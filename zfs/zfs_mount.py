#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    root_dataset = "tank/secure"
    if zfs_value(root_dataset, "keystatus") == "unavailable":
        run(["/usr/sbin/zfs", "load-key", root_dataset])
    run(["/usr/sbin/zfs", "mount", "-a"])
    return 0


def zfs_value(dataset: str, property_name: str) -> str:
    result = run(
        ["/usr/sbin/zfs", "get", "-H", "-o", "value", property_name, dataset]
    )
    return result.stdout.strip()


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise MountError(detail or f"Command failed with status {result.returncode}")
    return result


class MountError(RuntimeError):
    pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MountError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
