"""TPM unlock enrollment and checks for the boot_integrity stage."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import tpm_nv
from boot_settings import AUTHORIZE_USB_SCRIPT, ENROLLMENT, INITRD_INVENTORY, INVENTORY_SCRIPT, ROOT_USB_RULES, UKI_LIBRARY, UNLOCK_RESULT, load_settings
from install_helpers import LUKS_KEY_FILE, LUKS_PASSPHRASE_FILE, InstallerError, atomic_write, prompt_bool, prompt_choice, prompt_secret

CRYPTTAB = Path("/etc/crypttab")
TPM_DEVICE = Path("/dev/tpmrm0")
SECURE_BOOT_VARIABLE = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
STUB_VARIABLE = Path("/sys/firmware/efi/efivars/StubInfo-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f")
LUKS_SLOT = "7"
USB_DEVICE = re.compile(r"\d+-[\d.]+")
USB_STORAGE_CLASS = "08"
USB_HUB_CLASS = "09"
HELD_PACKAGES = ("linux-generic", "linux-image-generic", "linux-firmware", "intel-microcode", "dracut", "dracut-core", "systemd-ukify", "systemd-boot-efi")


def enroll_boot_integrity(configuration: Mapping[str, Any]) -> str:
    """Arm the TPM unlock from the booted, signed UKI and return a one-line status."""
    blocker = enrollment_blocker()
    if blocker:
        return f"pending: {blocker}"
    if tpm_nv.state() == "armed":
        return "enrolled" if unlock_result() == "unlocked" else "enrolled; reboot to verify the unattended unlock"
    build = booted_build()
    inventory = live_inventory()
    require_matching_initrd_view(inventory)
    gateway = choose_gateway(configuration)
    if not confirm_enrollment(inventory, gateway):
        return "pending: enrollment declined"
    passphrase = prompt_secret("LUKS recovery passphrase", confirm=False)
    arm(configuration, build, inventory, gateway, passphrase)
    return "enrolled; reboot to verify the unattended unlock"


def validation_failures(configuration: Mapping[str, Any]) -> list[str]:
    """Return one message per unmet requirement of an armed, verified boot-integrity setup."""
    failures: list[str] = []
    settings = load_settings()
    command_line = Path("/proc/cmdline").read_text().split()
    checks = [
        (secure_boot_enabled(), "Secure Boot is off"),
        (STUB_VARIABLE.exists(), "The host was not booted from a UKI"),
        (TPM_DEVICE.exists(), "No TPM 2.0 resource manager device"),
        (safe_state() == "armed", f"The unlock state is {safe_state()}; boot the signed UKI and rerun the installer"),
        (unlock_result() == "unlocked", f"The last boot did not unlock unattended ({unlock_result()})"),
        (all(token in command_line for token in settings["COMMAND_LINE"].split()), "The kernel command line lacks a managed token"),
        (Path("/proc/sys/kernel/sysrq").read_text().strip() == "0", "Magic SysRq is enabled"),
        (service_active("private-cloud-tripwire.service"), "The tripwire service is not running"),
        (not Path("/run/private-cloud/console-allowed").exists(), "The console accepts logins while the unlock is armed"),
        (not initrd_view_differences(), "The initrd hardware inventory differs from the running system"),
        (installed_root_usb_rules().strip() == root_usb_rules().strip(), "The root disk USB rules do not match the root disk path"),
        (not unexpected_root_usb_interfaces(), "The root disk USB path has authorized interfaces outside storage and hubs"),
        (Path("/etc/apt/apt.conf.d/52private-cloud-boot-chain").exists(), "Automatic boot-chain updates are not blocked"),
        (not unheld_packages(), f"Boot-chain packages are not held: {', '.join(unheld_packages())}"),
    ]
    failures.extend(message for passed, message in checks if not passed)
    return failures


def luks_volume() -> str:
    return luks_target()[1]


def enrollment_blocker() -> str | None:
    if not TPM_DEVICE.exists():
        return "the host has no TPM 2.0 device"
    if not secure_boot_enabled():
        return "Secure Boot is off"
    if not STUB_VARIABLE.exists():
        return next_uki_step()
    return None


def next_uki_step() -> str:
    builds = sorted(UKI_LIBRARY.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime)
    if not builds:
        return "the unsigned UKI has not been built; rerun the installer"
    directory = builds[-1].parent
    if (directory / "signed.efi").exists():
        return "reboot into the installed signed UKI, then rerun the installer"
    return f"sign {directory / 'unsigned.efi'} on the workstation, copy it to {directory / 'signed.efi'}, and rerun the installer"


def booted_build() -> dict[str, str]:
    live = tpm_nv.read_pcr(tpm_nv.MEASURED_PCR).hex()
    for manifest in UKI_LIBRARY.glob("*/manifest.json"):
        build = json.loads(manifest.read_text())
        if build["pcr11_ready"] == live:
            return build
    raise InstallerError("No built UKI matches the booted PCR 11; build, sign, install, and boot the current UKI")


def live_inventory() -> str:
    return run([str(INVENTORY_SCRIPT)]).stdout.rstrip("\n")


def require_matching_initrd_view(inventory: str) -> None:
    differences = initrd_view_differences(inventory)
    if differences:
        raise InstallerError(f"The initrd sees different hardware than the running system; add drivers to boot_integrity.extra_drivers: {', '.join(differences)}")


def initrd_view_differences(inventory: str | None = None) -> list[str]:
    if not INITRD_INVENTORY.exists():
        return ["no initrd inventory snapshot"]
    live = set(stable_lines(inventory if inventory is not None else live_inventory()))
    initrd = set(stable_lines(INITRD_INVENTORY.read_text()))
    return sorted(live ^ initrd)


def stable_lines(inventory: str) -> list[str]:
    return [line for line in inventory.splitlines() if line and not line.startswith("usb ")]


def choose_gateway(configuration: Mapping[str, Any]) -> str:
    result = subprocess.run(
        ["arping", "-c", "3", "-w", "3", "-I", configuration["interface"], configuration["gateway_ip"]],
        capture_output=True, text=True, check=False,
    )
    macs = sorted({mac.replace(":", "").lower() for mac in re.findall(r"\[([0-9A-Fa-f:]+)\]", result.stdout)})
    if not macs:
        raise InstallerError(f"The gateway {configuration['gateway_ip']} did not answer ARP on {configuration['interface']}")
    return macs[0] if len(macs) == 1 else prompt_choice("Gateway MAC address", macs, macs[0])


def confirm_enrollment(inventory: str, gateway: str) -> bool:
    usb_devices = [line for line in inventory.splitlines() if line.startswith("usb ")]
    print(f"Gateway MAC address: {gateway}")
    print("USB devices that will be bound to the unlock:\n  " + "\n  ".join(usb_devices))
    return prompt_bool("Unplug every external USB device except the root disk path first; enroll with exactly these devices", False)


def arm(configuration: Mapping[str, Any], build: Mapping[str, str], inventory: str, gateway: str, passphrase: str) -> None:
    device, _ = luks_target()
    salt, key = secrets.token_hex(32), secrets.token_hex(32)
    measured = {index: tpm_nv.read_pcr(index) for index in pcr_selection(configuration)}
    measured[tpm_nv.MEASURED_PCR] = bytes.fromhex(build["pcr11_enter_initrd"])
    measurement = hashlib.sha256(f"{salt}\n{inventory}\n{gateway}\n".encode()).digest()
    record = bytes.fromhex(salt) + bytes.fromhex(gateway) + hashlib.sha256(f"{inventory}\n".encode()).digest()
    record_policy = tpm_nv.policy_digest(measured)
    key_policy = tpm_nv.policy_digest({**measured, tpm_nv.INVENTORY_PCR: tpm_nv.inventory_pcr_value(measurement)})
    replace_luks_slot(device, passphrase, key)
    tpm_nv.provision(record_policy, key_policy, record, key.encode())
    expected = {str(index): value.hex() for index, value in measured.items()}
    description = {"build": build["name"], "gateway_mac": gateway, "expected_pcrs": expected, "enrolled_at": datetime.now(timezone.utc).isoformat()}
    atomic_write(ENROLLMENT, json.dumps(description, indent=2) + "\n", 0o600)
    tpm_nv.set_state(True)


def replace_luks_slot(device: str, passphrase: str, key: str) -> None:
    old, new = LUKS_PASSPHRASE_FILE, LUKS_KEY_FILE
    try:
        atomic_write(old, passphrase, 0o600)
        atomic_write(new, key, 0o600)
        run(["cryptsetup", "open", "--test-passphrase", f"--key-file={old}", device])
        subprocess.run(["cryptsetup", "luksKillSlot", f"--key-file={old}", device, LUKS_SLOT], capture_output=True, check=False)
        run(["cryptsetup", "luksAddKey", f"--key-file={old}", f"--key-slot={LUKS_SLOT}", "--pbkdf=pbkdf2", "--pbkdf-force-iterations=1000", device, str(new)])
        run(["cryptsetup", "open", "--test-passphrase", f"--key-slot={LUKS_SLOT}", f"--key-file={new}", device])
    finally:
        old.unlink(missing_ok=True)
        new.unlink(missing_ok=True)


def pcr_selection(configuration: Mapping[str, Any]) -> list[int]:
    return sorted({*tpm_nv.BASE_PCRS, *configuration["extra_pcrs"]})


def luks_target() -> tuple[str, str]:
    entries = [line.split() for line in CRYPTTAB.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(entries) != 1 or len(entries[0]) < 3 or entries[0][2] not in {"none", "-"}:
        raise InstallerError("/etc/crypttab must contain exactly one LUKS volume without a key file")
    name, source = entries[0][0], entries[0][1]
    return (f"/dev/disk/by-uuid/{source[5:]}" if source.startswith("UUID=") else source), name


def root_usb_authorizations() -> list[tuple[str, str]]:
    """Return each USB device from the root hub to a USB root disk with the only interface class it may bind."""
    path = root_usb_path()
    return [(device.name, USB_STORAGE_CLASS if device == path[-1] else USB_HUB_CLASS) for device in path]


def root_usb_rules() -> str:
    """Return udev rules that authorize only the storage path of a USB root disk; an internal disk needs none."""
    return "".join(usb_rule(Path("/sys/bus/usb/devices", name), interface_class) for name, interface_class in root_usb_authorizations())


def installed_root_usb_rules() -> str:
    return ROOT_USB_RULES.read_text() if ROOT_USB_RULES.exists() else ""


def unexpected_root_usb_interfaces() -> list[str]:
    found = []
    for name, interface_class in root_usb_authorizations():
        for interface in Path("/sys/bus/usb/devices", name).glob(f"{name}:*"):
            if usb_attribute(interface, "authorized") == "1" and usb_attribute(interface, "bInterfaceClass") != interface_class:
                found.append(interface.name)
    return found


def secure_boot_enabled() -> bool:
    try:
        return SECURE_BOOT_VARIABLE.read_bytes()[-1] == 1
    except OSError:
        return False


def safe_state() -> str:
    try:
        return tpm_nv.state()
    except (tpm_nv.TpmError, OSError):
        return "unreadable"


def unlock_result() -> str:
    try:
        return UNLOCK_RESULT.read_text().strip()
    except OSError:
        return "unknown"


def service_active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit], check=False).returncode == 0


def unheld_packages() -> list[str]:
    release = platform.release()
    names = [*HELD_PACKAGES, f"linux-image-{release}", f"linux-modules-{release}"]
    installed = run(["dpkg-query", "-W", "-f=${Package} ${db:Status-Abbrev}\\n", *names], check=False).stdout.splitlines()
    return [line.split()[0] for line in installed if line.endswith(" ii ")]


def run(arguments: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise InstallerError(f"{arguments[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result


def root_usb_path() -> list[Path]:
    block = Path(luks_target()[0]).resolve().name
    device = Path("/sys/class/block", block).resolve()
    return [parent for parent in reversed(device.parents) if USB_DEVICE.fullmatch(parent.name)]


def usb_rule(device: Path, interface_class: str) -> str:
    values = {name: usb_attribute(device, name) for name in ("idVendor", "idProduct", "serial")}
    if any(not re.fullmatch(r"[\x21-\x7e ]*", value) or '"' in value for value in values.values()):
        raise InstallerError(f"The USB device {device.name} on the root disk path reports identifiers that a udev rule cannot match")
    matches = [f'KERNEL=="{device.name}"', *(f'ATTR{{{name}}}=="{value}"' for name, value in values.items() if value)]
    return f'ACTION=="add", SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", {", ".join(matches)}, RUN+="{AUTHORIZE_USB_SCRIPT} %k {interface_class}"\n'


def usb_attribute(device: Path, name: str) -> str:
    try:
        return (device / name).read_text().strip()
    except OSError:
        return ""
