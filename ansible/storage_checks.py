#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


def main() -> int:
    arguments = parse_arguments()
    if arguments.check == "pool-layout":
        check_pool_layout(arguments.pool, arguments.disks)
    elif arguments.check == "disk-safety":
        check_disk_safety(arguments.disk, arguments.require_symlink, arguments.require_disk, arguments.resolve_swap, arguments.zfs_guard)
    elif arguments.check == "encrypted-mounts":
        check_encrypted_mounts(arguments.dataset)
    else:
        check_k0s_mounts(arguments.service, arguments.mountpoints)
    return 0


def check_pool_layout(pool: str, disks: list[str]) -> None:
    status = output("zpool", "status", "-P", "-L", pool)
    vdevs = [
        fields[0]
        for fields in (line.split() for line in status.splitlines())
        if fields and _is_vdev(fields[0])
    ]
    if len(vdevs) != 1 or not _is_raidz1(vdevs[0]):
        raise CheckError("pool topology is not one raidz1 vdev")
    members = [
        fields[0]
        for fields in (line.split() for line in status.splitlines())
        if len(fields) >= 2 and fields[0].startswith("/dev/") and fields[1] == "ONLINE"
    ]
    actual = sorted(str(Path(member).resolve(strict=True)) for member in members)
    expected = sorted(str(Path(disk).resolve(strict=True)) for disk in disks)
    if not actual or actual != expected:
        raise CheckError("pool members do not match selected disks")


def check_disk_safety(disk: str, require_symlink: bool, require_disk: bool, resolve_swap: bool, zfs_guard: bool) -> None:
    path = Path(disk)
    if require_symlink and not path.is_symlink():
        raise CheckError("disk path is not a symlink")
    if require_disk and output("lsblk", "-dn", "-o", "TYPE", disk).strip() != "disk":
        raise CheckError("disk path is not a whole disk")
    if _mountpoints(disk, zfs_guard).strip():
        raise CheckError("disk has mounted filesystems")
    if any(line == "swap" for line in _filesystems(disk, zfs_guard).splitlines()):
        raise CheckError("disk has a swap filesystem")
    pool_members = _pool_members()
    for device in _devices(disk, zfs_guard).splitlines():
        if _is_active_swap(device, resolve_swap):
            raise CheckError("disk is active swap")
        resolved = Path(device).resolve(strict=True)
        holder_directory = Path("/sys/class/block") / resolved.name / "holders"
        if any(holder_directory.iterdir()):
            raise CheckError("disk has holders")
        if str(resolved) in pool_members:
            raise CheckError("disk belongs to an imported pool")


def check_encrypted_mounts(dataset: str) -> None:
    for line in output("zfs", "list", "-H", "-r", "-o", "name,mountpoint,encroot", dataset).splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not fields[0] or fields[2] == "-":
            continue
        _require_key_unit(fields[1])


def check_k0s_mounts(service: str, mountpoints: list[str]) -> None:
    requires = output("systemctl", "show", "--value", "-p", "Requires", service).split()
    after = output("systemctl", "show", "--value", "-p", "After", service).split()
    for mountpoint in mountpoints:
        unit = output("systemd-escape", "--path", "--suffix=mount", mountpoint).strip()
        if unit not in requires or unit not in after:
            raise CheckError(f"{service} does not depend on {unit}")


def _require_key_unit(mountpoint: str) -> None:
    unit = output("systemd-escape", "--path", "--suffix=mount", mountpoint).strip()
    requires = output("systemctl", "show", "--value", "-p", "Requires", unit).split()
    after = output("systemctl", "show", "--value", "-p", "After", unit).split()
    key_unit = "zfs-load-key@tank-secure.service"
    if key_unit not in requires or key_unit not in after:
        raise CheckError(f"{unit} does not depend on {key_unit}")


def _mountpoints(disk: str, zfs_guard: bool) -> str:
    if zfs_guard:
        return output("lsblk", "-nr", "-o", "MOUNTPOINTS", disk)
    return output("lsblk", "-nrpo", "MOUNTPOINT", disk)


def _filesystems(disk: str, zfs_guard: bool) -> str:
    if zfs_guard:
        return output("lsblk", "-nr", "-o", "FSTYPE", disk)
    return output("lsblk", "-nrpo", "FSTYPE", disk)


def _devices(disk: str, zfs_guard: bool) -> str:
    if zfs_guard:
        return output("lsblk", "-nr", "-o", "PATH", disk)
    return output("lsblk", "-nrpo", "NAME", disk)


def _is_active_swap(device: str, resolve_swap: bool) -> bool:
    swaps = output("swapon", "--noheadings", "--raw", "--show=NAME").splitlines()
    if not resolve_swap:
        return device in swaps
    resolved = str(Path(device).resolve(strict=True))
    return any(str(Path(swap).resolve(strict=True)) == resolved for swap in swaps)


def _pool_members() -> set[str]:
    
    try:
        result = subprocess.run(["zpool", "status", "-L", "-P"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return set()
    return {
        str(Path(line.split()[0]).resolve(strict=True))
        for line in result.stdout.splitlines()
        if line.split() and line.split()[0].startswith("/dev/")
    }


def output(*command: str) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise CheckError(" ".join(command))
    return result.stdout


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=("pool-layout", "disk-safety", "encrypted-mounts", "k0s-mounts"))
    parser.add_argument("--pool")
    parser.add_argument("--disk")
    parser.add_argument("--disks", nargs="*")
    parser.add_argument("--dataset")
    parser.add_argument("--service")
    parser.add_argument("--mountpoints", nargs="*")
    parser.add_argument("--require-symlink", action="store_true")
    parser.add_argument("--require-disk", action="store_true")
    parser.add_argument("--resolve-swap", action="store_true")
    parser.add_argument("--zfs-guard", action="store_true")
    arguments = parser.parse_args()
    if arguments.check == "pool-layout" and (not arguments.pool or not arguments.disks):
        parser.error("pool layout requires a pool and disks")
    if arguments.check == "disk-safety" and not arguments.disk:
        parser.error("disk safety requires a disk")
    if arguments.check == "encrypted-mounts" and not arguments.dataset:
        parser.error("encrypted mounts requires a dataset")
    if arguments.check == "k0s-mounts" and (not arguments.service or not arguments.mountpoints):
        parser.error("k0s mounts requires a service and mountpoints")
    return arguments


def _is_vdev(value: str) -> bool:
    return bool(re.fullmatch(r"mirror(?:-[0-9]+)?|raidz[0-9]+(?:-[0-9]+)?|draid(?:[0-9]+)?(?:-[0-9]+)?|spares|logs|cache|special|dedup", value))


def _is_raidz1(value: str) -> bool:
    return bool(re.fullmatch(r"raidz1(?:-[0-9]+)?", value))


class CheckError(Exception):
    pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckError as error:
        raise SystemExit(str(error)) from error
