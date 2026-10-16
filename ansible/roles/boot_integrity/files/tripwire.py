#!/usr/bin/env python3
"""Runtime tripwire for the TPM unlock: wipes the secret and powers off on a new device or another gateway."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tpm_nv
from boot_settings import CONSOLE_FLAG, ENROLLMENT, load_settings

POLL_SECONDS = 0.5
GATEWAY_SECONDS = 30


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command == "armed":
        return 0 if current_state() == "armed" else 1
    if command == "console":
        allow_console()
        return 0
    if command == "run":
        watch()
        return 0
    return 2


def allow_console() -> None:
    """The console accepts logins only while the unlock secret is not armed."""
    if current_state() == "armed":
        return
    CONSOLE_FLAG.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    CONSOLE_FLAG.touch()


def watch() -> None:
    settings = load_settings()
    gateway = json.loads(ENROLLMENT.read_text())["gateway_mac"]
    baseline = devices()
    next_gateway = time.monotonic() + GATEWAY_SECONDS
    while True:
        if devices() - baseline:
            trip("new-device")
            return
        if time.monotonic() >= next_gateway:
            next_gateway = time.monotonic() + GATEWAY_SECONDS
            macs = gateway_macs(settings["INTERFACE"], settings["GATEWAY_IP"])
            if macs and gateway not in macs:
                trip("gateway-mismatch")
                return
        time.sleep(POLL_SECONDS)


def trip(reason: str) -> None:
    print(f"private-cloud-tripwire: {reason}; wiping the unlock secret and powering off", flush=True)
    try:
        tpm_nv.wipe()
    finally:
        subprocess.run(["systemctl", "poweroff", "--force"], check=False)


def current_state() -> str:
    try:
        return tpm_nv.state()
    except (tpm_nv.TpmError, OSError):
        return "armed"


def devices() -> set[tuple[str, ...]]:
    found: set[tuple[str, ...]] = set()
    for device in Path("/sys/bus/usb/devices").glob("*"):
        if (device / "idVendor").exists():
            found.add(("usb", device.name, attribute(device, "idVendor"), attribute(device, "idProduct"), attribute(device, "serial")))
    for device in Path("/sys/bus/pci/devices").glob("*"):
        found.add(("pci", device.name, attribute(device, "vendor"), attribute(device, "device")))
    return found


def attribute(device: Path, name: str) -> str:
    try:
        return (device / name).read_text().strip()
    except OSError:
        return ""


def gateway_macs(interface: str, gateway: str) -> set[str]:
    result = subprocess.run(
        ["arping", "-c", "1", "-w", "2", "-I", interface, gateway], capture_output=True, text=True, check=False
    )
    return {mac.replace(":", "").lower() for mac in re.findall(r"\[([0-9A-Fa-f:]+)\]", result.stdout)}


if __name__ == "__main__":
    raise SystemExit(main())
