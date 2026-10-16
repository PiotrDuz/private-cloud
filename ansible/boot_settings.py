"""Paths and managed settings shared by the installer and the host helpers of the boot_integrity stage."""

from __future__ import annotations

import re
from pathlib import Path

CONFIGURATION = Path("/etc/private-cloud/boot-integrity.conf")
ENROLLMENT = Path("/var/lib/private-cloud/boot-integrity.json")
UKI_LIBRARY = Path("/var/lib/private-cloud/uki")
HELPERS = Path("/usr/local/libexec/private-cloud")
RUN = Path("/run/private-cloud")
UNLOCK_RESULT = RUN / "unlock-result"
INITRD_INVENTORY = RUN / "initrd-inventory"
CONSOLE_FLAG = RUN / "console-allowed"
INVENTORY_SCRIPT = HELPERS / "inventory.sh"


def load_settings() -> dict[str, str]:
    """Parse the KEY=value lines that the initrd hook also sources."""
    pairs = re.findall(r"^([A-Z_]+)=(.*)$", CONFIGURATION.read_text(), re.MULTILINE)
    return {key: value.strip().strip('"') for key, value in pairs}
