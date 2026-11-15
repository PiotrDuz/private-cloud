#!/usr/bin/env python3
"""Collect the boot integrity unlock, Secure Boot, and tripwire state for Zabbix Agent 2."""

import json
import subprocess
import time
from pathlib import Path

from collector_logging import log_collector_errors


UNLOCK_RESULT = Path("/run/private-cloud/unlock-result")
TRIPWIRE_RESULT = Path("/var/lib/private-cloud/tripwire-result")
ENROLLMENT = Path("/var/lib/private-cloud/boot-integrity.json")
SECURE_BOOT = Path("/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c")
TRIPWIRE_UNIT = "private-cloud-tripwire.service"
UNLOCK_CODES = {"unlocked": 0, "inert": 1, "wiped": 2, "error": 3, "wipe-failed": 4}
UNLOCK_MISSING = 5
UNLOCK_UNKNOWN = 6


def main():
    errors = []
    try:
        unlock = read_text(UNLOCK_RESULT, errors)
        tripwire = read_text(TRIPWIRE_RESULT, errors)
        result = {
            "generated_at": int(time.time()),
            "unlock_result": unlock,
            "unlock_code": unlock_code(unlock),
            "secure_boot": secure_boot(errors),
            "tripwire_active": tripwire_active(),
            "tripwire_result": tripwire,
            "tripwire_pending": int(bool(tripwire) and newer_than_enrollment(errors)),
            "error_count": len(errors),
            "errors": errors,
        }
    except Exception as error:
        log_collector_errors("boot-integrity", [f"collector failed: {error}"])
        raise
    log_collector_errors("boot-integrity", errors)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


def unlock_code(unlock):
    if not unlock:
        return UNLOCK_MISSING
    return UNLOCK_CODES.get(unlock.split(":", 1)[0], UNLOCK_UNKNOWN)


def secure_boot(errors):
    try:
        return int(SECURE_BOOT.read_bytes()[4:5] == b"\x01")
    except FileNotFoundError:
        return 0
    except OSError as error:
        errors.append(f"cannot read {SECURE_BOOT}: {error}")
        return 0


def tripwire_active():
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", TRIPWIRE_UNIT], check=False, timeout=10
    )
    return int(result.returncode == 0)


# A trip stays pending until a re-enrollment rewrites the enrollment record.
def newer_than_enrollment(errors):
    try:
        return TRIPWIRE_RESULT.stat().st_mtime > ENROLLMENT.stat().st_mtime
    except FileNotFoundError:
        return True
    except OSError as error:
        errors.append(f"cannot stat the tripwire or enrollment record: {error}")
        return True


def read_text(path, errors):
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except FileNotFoundError:
        return ""
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


if __name__ == "__main__":
    main()
