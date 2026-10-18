#!/usr/bin/env python3
"""Builds the unsigned UKI with its PCR 11 manifest and installs the operator-signed UKI on the ESP."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boot_settings import AUTHORIZE_USB_SCRIPT, CONFIGURATION, HELPERS, ROOT_USB_RULES, UKI_LIBRARY, load_settings

MODULE_DIRECTORY = Path("/usr/lib/dracut/modules.d/90private-cloud-tpm")
DRACUT_CONFIGURATION = Path("/etc/dracut.conf.d/90-private-cloud.conf")
ESP = Path("/boot/efi")
ESP_FILE = ESP / "EFI/Linux/private-cloud.efi"
BOOT_LABEL = "private-cloud"
STUB = Path("/usr/lib/systemd/boot/efi/linuxx64.efi.stub")
READY_PHASE = "enter-initrd:leave-initrd:sysinit:ready"


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "build":
        print(build())
        return 0
    if command == "install":
        print(install())
        return 0
    return 2


def build() -> str:
    kernel = platform.release()
    command_line = kernel_command_line()
    name = f"{kernel}-{inputs_digest(kernel, command_line)[:12]}"
    directory = UKI_LIBRARY / name
    if (directory / "manifest.json").exists():
        return f"current {name}"
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    shutil.copyfile(f"/boot/vmlinuz-{kernel}", directory / "linux")
    shutil.copyfile("/etc/os-release", directory / "osrel")
    (directory / "cmdline").write_text(command_line)
    (directory / "uname").write_text(kernel)
    run(["dracut", "--force", "--reproducible", "--no-hostonly-cmdline", "--kver", kernel, "--add", "private-cloud-tpm", str(directory / "initrd")])
    phases = build_unsigned(directory, kernel)
    manifest = {"name": name, "kernel": kernel, "pcr11_enter_initrd": phases["enter-initrd"], "pcr11_ready": phases[READY_PHASE]}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return f"built {name}"


def install() -> str:
    candidates = sorted(UKI_LIBRARY.glob("*/signed.efi"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        return "no-signed-uki"
    signed = candidates[-1]
    ESP_FILE.parent.mkdir(parents=True, exist_ok=True)
    changed = not ESP_FILE.exists() or digest(ESP_FILE) != digest(signed)
    if changed:
        temporary = ESP_FILE.with_suffix(".new")
        shutil.copyfile(signed, temporary)
        temporary.replace(ESP_FILE)
    changed = ensure_boot_entry() or changed
    return f"{'installed' if changed else 'current'} {signed.parent.name}"


def kernel_command_line() -> str:
    settings = load_settings()
    required = settings["COMMAND_LINE"].split()
    managed = {token.split("=", 1)[0] for token in required}
    tokens = [token for token in Path("/proc/cmdline").read_text().split()
              if not token.startswith(("BOOT_IMAGE=", "initrd=")) and token.split("=", 1)[0] not in managed]
    return " ".join(tokens + required)


def inputs_digest(kernel: str, command_line: str) -> str:
    result = hashlib.sha256(f"{kernel}\n{command_line}\n".encode())
    paths = [Path(f"/boot/vmlinuz-{kernel}"), CONFIGURATION, DRACUT_CONFIGURATION, Path("/etc/crypttab"), Path("/etc/os-release"),
             HELPERS / "inventory.sh", AUTHORIZE_USB_SCRIPT, *sorted(MODULE_DIRECTORY.glob("*"))]
    result.update(ROOT_USB_RULES.read_bytes() if ROOT_USB_RULES.exists() else b"internal root disk\n")
    for path in paths:
        result.update(digest(path).encode())
    return result.hexdigest()


def build_unsigned(directory: Path, kernel: str) -> dict[str, str]:
    """Build the image and return its PCR 11 values; ukify measures the exact section set it embeds, including .sbat."""
    result = run([ukify(), "build", f"--linux={directory / 'linux'}", f"--initrd={directory / 'initrd'}", f"--cmdline=@{directory / 'cmdline'}",
                  f"--os-release=@{directory / 'osrel'}", f"--uname={kernel}", f"--stub={STUB}", f"--output={directory / 'unsigned.efi'}",
                  "--pcr-banks=sha256", "--measure", "--json=short"])
    return {entry["phase"]: entry["hash"] for entry in json.loads(result.stdout)["sha256"]}


def ensure_boot_entry() -> bool:
    if re.search(rf"^Boot[0-9A-F]{{4}}\*?\s+{BOOT_LABEL}\b", run(["efibootmgr"]).stdout, re.MULTILINE):
        return False
    source = run(["findmnt", "-no", "SOURCE", str(ESP)]).stdout.strip()
    disk = run(["lsblk", "-no", "PKNAME", source]).stdout.strip()
    partition = Path(f"/sys/class/block/{Path(source).name}/partition").read_text().strip()
    run(["efibootmgr", "--create", "--disk", f"/dev/{disk}", "--part", partition, "--label", BOOT_LABEL, "--loader", "\\EFI\\Linux\\private-cloud.efi"])
    return True


def ukify() -> str:
    return shutil.which("ukify") or "/usr/lib/systemd/ukify"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
