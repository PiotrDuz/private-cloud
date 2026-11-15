#!/usr/bin/env python3
"""Runtime tripwire for the TPM unlock: wipes the secret and powers off on a device outside the enrollment or another gateway."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tpm_nv
from boot_settings import CONSOLE_FLAG, ENROLLMENT, INVENTORY_SCRIPT, TRIPWIRE_RESULT, device_lines, load_settings

POLL_SECONDS = 0.5
GATEWAY_SECONDS = 30
INVENTORY_SECONDS = 5


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
    enrollment = json.loads(ENROLLMENT.read_text())
    gateway, enrolled = enrollment["gateway_mac"], set(enrollment["devices"])
    names: set[str] = set()
    next_gateway = next_inventory = time.monotonic()
    while True:
        # The cheap sysfs listing triggers a full inventory at once; a periodic one catches a device that appeared half-populated.
        current = device_names()
        if current != names or time.monotonic() >= next_inventory:
            names, next_inventory = current, time.monotonic() + INVENTORY_SECONDS
            added = devices() - enrolled
            if added:
                trip("new-device " + "; ".join(sorted(added)))
                return
        if time.monotonic() >= next_gateway:
            next_gateway = time.monotonic() + GATEWAY_SECONDS
            macs = gateway_macs(settings["INTERFACE"], settings["GATEWAY_IP"])
            if macs and gateway not in macs:
                trip("gateway-mismatch")
                return
        time.sleep(POLL_SECONDS)


def trip(reason: str) -> None:
    try:
        try:
            tpm_nv.wipe()
            outcome = "wipe verified"
        except (tpm_nv.TpmError, OSError) as error:
            outcome = f"wipe failed: {error}"
        print(f"private-cloud-tripwire: {reason}; {outcome}; powering off", flush=True)
        TRIPWIRE_RESULT.write_text(f"{datetime.now(timezone.utc).isoformat()} {outcome}: {reason}\n")
        os.sync()
    finally:
        subprocess.run(["systemctl", "poweroff", "--force"], check=False)


def current_state() -> str:
    try:
        return tpm_nv.state()
    except (tpm_nv.TpmError, OSError):
        return "armed"


def devices() -> set[str]:
    """Return the USB and PCI lines exactly as the enrollment recorded them from the same inventory script."""
    inventory = subprocess.run([str(INVENTORY_SCRIPT)], capture_output=True, text=True, check=True).stdout
    return set(device_lines(inventory))


def device_names() -> set[str]:
    return {path.name for bus in ("usb", "pci") for path in Path(f"/sys/bus/{bus}/devices").iterdir()}


def gateway_macs(interface: str, gateway: str) -> set[str]:
    result = subprocess.run(
        ["arping", "-c", "1", "-w", "2", "-I", interface, gateway], capture_output=True, text=True, check=False
    )
    return {mac.replace(":", "").lower() for mac in re.findall(r"\[([0-9A-Fa-f:]+)\]", result.stdout)}


if __name__ == "__main__":
    raise SystemExit(main())
