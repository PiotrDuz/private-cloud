from __future__ import annotations

import getpass
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import (  # noqa: E402
    InstallerError,
    read_os_release,
    require_commands,
)

LSBLK_COLUMNS = [
    "NAME",
    "PATH",
    "KNAME",
    "TYPE",
    "SIZE",
    "MODEL",
    "SERIAL",
    "TRAN",
    "FSTYPE",
    "MOUNTPOINTS",
    "RO",
]


def load_block_devices(
    runner: CommandRunner,
    device: Path | None = None,
) -> list[dict[str, Any]]:
    args = [
        "lsblk",
        "--json",
        "--bytes",
        "--paths",
        "--output",
        ",".join(LSBLK_COLUMNS),
    ]
    if device is not None:
        args.append(str(device))

    result = runner.capture(args)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstallerError("lsblk returned invalid JSON") from error
    return data.get("blockdevices", [])


def walk_devices(device: dict[str, Any]) -> list[dict[str, Any]]:
    devices = [device]
    for child in device.get("children") or []:
        devices.extend(walk_devices(child))
    return devices


def active_pool_members(runner: CommandRunner) -> set[Path]:
    if shutil.which("zpool") is None:
        return set()

    result = runner.capture(["zpool", "status", "-LP"], check=False)
    members: set[Path] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[0].startswith("/dev/"):
            members.add(Path(os.path.realpath(fields[0])))
    return members


def active_reason(
    device: dict[str, Any],
    pool_members: set[Path],
) -> str | None:
    descendants = walk_devices(device)
    device_paths = {
        Path(os.path.realpath(str(item["path"])))
        for item in descendants
        if item.get("path")
    }

    for item in descendants:
        mountpoints = item.get("mountpoints") or []
        if isinstance(mountpoints, str):
            mountpoints = [mountpoints]
        if any(mountpoint for mountpoint in mountpoints):
            return "mounted filesystem"
        if item.get("fstype") == "swap":
            return "swap signature"

        kname = os.path.basename(str(item.get("kname") or ""))
        holders = Path("/sys/class/block") / kname / "holders"
        if kname and holders.is_dir() and any(holders.iterdir()):
            return "active device-mapper or RAID holder"

    if device_paths & pool_members:
        return "member of an imported ZFS pool"
    return None


def stable_id_for_disk(disk_path: Path) -> Path | None:
    directory = Path("/dev/disk/by-id")
    if not directory.is_dir():
        return None

    choices: list[tuple[int, int, str, Path]] = []
    for link in directory.iterdir():
        if not link.is_symlink() or re.search(r"-part\d+$", link.name):
            continue
        target = Path(os.path.realpath(link))
        if target != disk_path:
            continue
        choices.append((stable_id_priority(link.name), len(link.name), link.name, link))

    return min(choices)[3] if choices else None


def stable_id_priority(name: str) -> int:
    prefixes = (
        ("nvme-eui.", 10),
        ("nvme-uuid.", 10),
        ("wwn-", 20),
        ("ata-", 30),
        ("scsi-", 40),
        ("virtio-", 50),
        ("nvme-", 60),
    )
    for prefix, priority in prefixes:
        if name.startswith(prefix):
            return priority
    return 70


def disk_note(device: dict[str, Any]) -> str:
    descendants = walk_devices(device)
    signatures = sorted(
        {
            str(item["fstype"])
            for item in descendants
            if item.get("fstype")
        }
    )
    if signatures:
        return f"contains {','.join(signatures)}"
    if any(item.get("type") == "part" for item in descendants):
        return "contains partitions"
    return "blank"


def pool_exists(runner: CommandRunner, pool_name: str) -> bool:
    if shutil.which("zpool") is None:
        return False

    result = runner.capture(
        ["zpool", "list", "-H", "-o", "name", pool_name],
        check=False,
    )
    if result.returncode == 0:
        return True

    result = runner.capture(
        ["zfs", "list", "-H", "-o", "name", pool_name],
        check=False,
    )
    return result.returncode == 0


def read_tty(tty: TextIO, prompt: str) -> str:
    tty.write(prompt)
    tty.flush()
    value = tty.readline()
    if value == "":
        raise InstallerError("Terminal input ended unexpectedly")
    return value.rstrip("\n")


def prompt_for_passphrase(
    tty: TextIO,
    dataset: str,
    key_file: Path,
) -> bytearray | None:
    print(f"\nChoose the passphrase for {dataset} (8-512 bytes).")
    print(f"It will not be displayed and will be stored in {key_file}.")
    while True:
        first = getpass.getpass("Passphrase: ", stream=tty)
        encoded = first.encode("utf-8")
        if not 8 <= len(encoded) <= 512:
            print(
                "WARNING: The passphrase must contain between 8 and 512 bytes",
                file=sys.stderr,
            )
            continue

        second = getpass.getpass("Confirm passphrase: ", stream=tty)
        if first != second:
            print("WARNING: Passphrases do not match; try again", file=sys.stderr)
            continue
        return bytearray(encoded)


def write_passphrase_file(path: Path, passphrase: bytearray) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as key_file:
            # No trailing newline is written, so recreating the exact bytes restores access.
            key_file.write(passphrase)
            key_file.flush()
            os.fsync(key_file.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def clear_secret(secret: bytearray | None) -> None:
    if secret is None:
        return
    for index in range(len(secret)):
        secret[index] = 0


def clean_field(value: Any) -> str:
    return " ".join(str(value or "").split())


def value_is_true(value: Any) -> bool:
    return value is True or str(value).lower() in {"1", "true", "yes"}


def human_size(size: int) -> str:
    value = float(size)
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def print_disk_row(
    index: str,
    path: Path,
    size: int,
    transport: str,
    model: str,
    serial: str,
    status: str,
) -> None:
    print(
        f"  {index:<3} {str(path):<14.14} {human_size(size):<9.9} "
        f"{transport:<8.8} {model:<24.24} {serial:<18.18} {status}"
    )


def report_partial_pool(
    state: InstallationState | None,
    pool_name: str,
) -> None:
    if state is not None and state.pool_created:
        print(
            f"The pool was not destroyed; inspect it with: zpool status -v {pool_name}",
            file=sys.stderr,
        )


@dataclass(frozen=True)
class Disk:
    path: Path
    stable_path: Path
    size: int
    model: str
    serial: str
    transport: str
    note: str


class CommandRunner:
    def run(
        self,
        args: list[str],
        *,
        check: bool = True,
        quiet: bool = False,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        print(f"  {shlex.join(args)}")
        return subprocess.run(
            args,
            check=check,
            text=True,
            stdout=subprocess.DEVNULL if quiet else None,
            stderr=subprocess.DEVNULL if quiet else None,
            env=env,
        )

    def capture(
        self,
        args: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            args,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


@dataclass
class InstallationState:
    tty: TextIO
    runner: CommandRunner
    passphrase: bytearray | None = None
    pool_created: bool = False
