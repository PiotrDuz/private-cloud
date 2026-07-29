#!/usr/bin/env python3
from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from zfs_setup_helpers import (
    CommandRunner,
    Disk,
    InstallationState,
    InstallerError,
    active_pool_members,
    active_reason,
    clean_field,
    clear_secret,
    disk_note,
    human_size,
    load_block_devices,
    pool_exists,
    print_disk_row,
    prompt_for_passphrase,
    read_os_release,
    read_tty,
    report_partial_pool,
    require_commands,
    stable_id_for_disk,
    value_is_true,
    write_passphrase_file,
)

POOL_NAME = "tank"
POOL_MOUNTPOINT = "/tank"
SECURE_DATASET = f"{POOL_NAME}/secure"
SECURE_MOUNTPOINT = f"{POOL_MOUNTPOINT}/secure"
KEY_DIRECTORY = Path("/etc/zfs/keys")
KEY_FILE = KEY_DIRECTORY / "tank-secure.key"
MINIMUM_DISKS = 3
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
MOUNT_HELPER_SOURCE = SCRIPT_DIRECTORY / "zfs_mount.py"
MOUNT_HELPER_TARGET = Path("/usr/local/sbin/zfs-unlock-mount")
MOUNT_SERVICE_SOURCE = SCRIPT_DIRECTORY / "zfs-unlock-mount.service"
MOUNT_SERVICE_TARGET = Path("/etc/systemd/system/zfs-unlock-mount.service")
SCRUB_SERVICE_SOURCE = SCRIPT_DIRECTORY / "zfs-scrub.service"
SCRUB_SERVICE_TARGET = Path("/etc/systemd/system/zfs-scrub.service")
SCRUB_TIMER_SOURCE = SCRIPT_DIRECTORY / "zfs-scrub.timer"
SCRUB_TIMER_TARGET = Path("/etc/systemd/system/zfs-scrub.timer")


def run_installation(state: InstallationState) -> None:
    preflight(state)
    disks = discover_disks(state)
    selected = select_disks(state, disks)
    state.passphrase = prompt_for_passphrase(
        state.tty,
        SECURE_DATASET,
        KEY_FILE,
    )
    show_plan(state, selected)
    confirm_plan(state)
    install_zfs(state)
    if pool_exists(state.runner, POOL_NAME):
        raise InstallerError(f"A ZFS pool or dataset named {POOL_NAME} already exists")
    validate_selected_disks(state, selected)
    erase_selected_disks(state, selected)
    create_pool(state, selected)
    create_secure_dataset(state)
    configure_services(state)
    show_result(state)


def preflight(state: InstallationState) -> None:
    if os.geteuid() != 0:
        raise InstallerError(f"Run this installer as root: sudo {sys.argv[0]}")

    require_commands(
        [
            "apt-get",
            "install",
            "lsblk",
            "modprobe",
            "systemctl",
            "udevadm",
            "wipefs",
        ]
    )

    distribution = read_os_release().get("ID", "")
    if distribution not in {"debian", "ubuntu"}:
        raise InstallerError(
            f"Only Debian and Ubuntu are supported; detected {distribution or 'unknown'}"
        )

    if KEY_FILE.exists():
        raise InstallerError(
            f"Key exists at {KEY_FILE}; verify it is no longer needed before moving it"
        )

    for source in (
        MOUNT_HELPER_SOURCE,
        MOUNT_SERVICE_SOURCE,
        SCRUB_SERVICE_SOURCE,
        SCRUB_TIMER_SOURCE,
    ):
        if not source.is_file():
            raise InstallerError(f"Required service file not found: {source}")

    if shutil.which("zpool") is not None and pool_exists(state.runner, POOL_NAME):
        raise InstallerError(f"A ZFS pool or dataset named {POOL_NAME} already exists")

    print("ZFS RAIDZ1 installer")
    print(f"This creates pool {POOL_NAME} and its root dataset on selected whole disks.")


def install_zfs(state: InstallationState) -> None:
    print("\nInstalling ZFS packages...")
    state.runner.run(["apt-get", "update"])
    environment = os.environ.copy()
    environment["DEBIAN_FRONTEND"] = "noninteractive"
    state.runner.run(
        ["apt-get", "install", "-y", "zfsutils-linux", "zfs-zed"],
        env=environment,
    )

    state.runner.run(["modprobe", "zfs"])
    require_commands(["zfs", "zpool"])
    state.runner.run(["zfs", "version"])


def discover_disks(state: InstallationState) -> list[Disk]:
    devices = [
        item
        for item in load_block_devices(state.runner)
        if item.get("type") == "disk"
    ]
    if not devices:
        raise InstallerError("No whole disks were discovered")

    pool_members = active_pool_members(state.runner)
    candidates: list[Disk] = []

    print("\nDiscovered whole disks:")
    print(
        f"  {'#':<3} {'DEVICE':<14} {'SIZE':<9} {'TRAN':<8} "
        f"{'MODEL':<24} {'SERIAL':<18} STATUS"
    )

    for device in sorted(devices, key=lambda item: str(item.get("path") or "")):
        path = Path(os.path.realpath(str(device["path"])))
        size = int(device.get("size") or 0)
        model = clean_field(device.get("model"))
        serial = clean_field(device.get("serial"))
        transport = clean_field(device.get("tran"))
        reason = active_reason(device, pool_members)
        stable_path = stable_id_for_disk(path)

        if value_is_true(device.get("ro")):
            reason = reason or "read-only device"
        if size <= 0:
            reason = reason or "zero-sized device"
        if stable_path is None:
            reason = reason or "no stable /dev/disk/by-id link"

        if reason:
            print_disk_row(
                "-",
                path,
                size,
                transport,
                model,
                serial,
                f"unavailable: {reason}",
            )
            continue

        disk = Disk(
            path=path,
            stable_path=stable_path,
            size=size,
            model=model,
            serial=serial,
            transport=transport,
            note=disk_note(device),
        )
        candidates.append(disk)
        print_disk_row(
            str(len(candidates)),
            path,
            size,
            transport,
            model,
            serial,
            f"selectable: {disk.note}",
        )
        print(f"      stable ID: {stable_path}")

    if len(candidates) < MINIMUM_DISKS:
        raise InstallerError(
            f"RAIDZ1 needs at least {MINIMUM_DISKS} selectable disks; "
            f"found {len(candidates)}"
        )
    return candidates


def select_disks(
    state: InstallationState,
    disks: list[Disk],
) -> list[Disk]:
    while True:
        print("\nRAIDZ1 tolerates one disk failure. Use similarly sized disks.")
        response = read_tty(
            state.tty,
            f"Select at least {MINIMUM_DISKS} disk numbers, "
            "separated by spaces (or q to quit): ",
        ).strip()
        if response.lower() == "q":
            raise KeyboardInterrupt

        indexes: list[int] = []
        invalid = False
        for token in response.split():
            if not token.isdecimal():
                print(f"WARNING: Invalid disk number: {token}", file=sys.stderr)
                invalid = True
                break
            index = int(token) - 1
            if index < 0 or index >= len(disks):
                print(f"WARNING: Invalid disk number: {token}", file=sys.stderr)
                invalid = True
                break
            if index not in indexes:
                indexes.append(index)

        if not invalid and len(indexes) >= MINIMUM_DISKS:
            return [disks[index] for index in indexes]
        print(
            f"WARNING: Select at least {MINIMUM_DISKS} different disks",
            file=sys.stderr,
        )


def show_plan(
    state: InstallationState,
    selected: list[Disk],
) -> None:
    smallest_size = min(disk.size for disk in selected)
    estimated_size = smallest_size * (len(selected) - 1)

    print("\nPlanned pool:")
    print(f"  Name:       {POOL_NAME}")
    print(f"  Mountpoint: {POOL_MOUNTPOINT}")
    print(f"  Topology:   RAIDZ1 ({len(selected)} disks)")
    print("  Members:")
    for disk in selected:
        print(
            f"    - {disk.stable_path} "
            f"({human_size(disk.size)}, {disk.model}, {disk.note})"
        )
    print(f"  Approximate raw RAIDZ1 capacity: {human_size(estimated_size)}")
    print(f"  Encrypted dataset: {SECURE_DATASET} at {SECURE_MOUNTPOINT}")
    print(f"  Passphrase file:  {KEY_FILE}")
    print("\nALL DATA ON THE SELECTED DISKS WILL BE PERMANENTLY ERASED.")


def confirm_plan(state: InstallationState) -> None:
    confirmation = read_tty(
        state.tty,
        f"Type CREATE {POOL_NAME} to approve the plan: ",
    )
    if confirmation != f"CREATE {POOL_NAME}":
        raise InstallerError("Confirmation did not match; no changes made")


def validate_selected_disks(
    state: InstallationState,
    selected: list[Disk],
) -> None:
    pool_members = active_pool_members(state.runner)
    for disk in selected:
        try:
            mode = disk.path.stat().st_mode
        except OSError as error:
            raise InstallerError(f"Selected disk disappeared: {disk.path}") from error
        if not stat.S_ISBLK(mode):
            raise InstallerError(f"Selected path is no longer a block device: {disk.path}")
        if Path(os.path.realpath(disk.stable_path)) != disk.path:
            raise InstallerError(
                f"Stable ID no longer resolves to the selected disk: {disk.stable_path}"
            )

        devices = load_block_devices(state.runner, disk.path)
        if not devices:
            raise InstallerError(f"Selected disk disappeared: {disk.path}")
        reason = active_reason(devices[0], pool_members)
        if reason:
            raise InstallerError(
                f"Selected disk became unavailable ({disk.path}: {reason})"
            )


def erase_selected_disks(
    state: InstallationState,
    selected: list[Disk],
) -> None:
    print("\nErasing signatures from selected disks...")
    for disk in selected:
        state.runner.run(
            ["zpool", "labelclear", "-f", str(disk.stable_path)],
            check=False,
            quiet=True,
        )
        state.runner.run(["wipefs", "--all", "--force", str(disk.stable_path)])
    state.runner.run(["udevadm", "settle"])


def create_pool(
    state: InstallationState,
    selected: list[Disk],
) -> None:
    members = [str(disk.stable_path) for disk in selected]
    print("\nCreating pool...")
    state.runner.run(
        [
            "zpool",
            "create",
            "-f",
            "-o",
            "ashift=12",
            "-o",
            "autotrim=on",
            "-O",
            "acltype=posixacl",
            "-O",
            "atime=off",
            "-O",
            "compression=zstd",
            "-O",
            "dnodesize=auto",
            "-O",
            f"mountpoint={POOL_MOUNTPOINT}",
            "-O",
            "normalization=formD",
            "-O",
            "xattr=sa",
            POOL_NAME,
            "raidz1",
            *members,
        ]
    )

    state.pool_created = True
    state.runner.run(["zpool", "set", "cachefile=/etc/zfs/zpool.cache", POOL_NAME])


def create_secure_dataset(state: InstallationState) -> None:
    print("\nCreating encrypted dataset...")
    state.runner.run(["install", "-d", "-m", "0700", str(KEY_DIRECTORY)])

    if state.passphrase is None:
        raise InstallerError("The dataset passphrase is unexpectedly empty")
    try:
        write_passphrase_file(KEY_FILE, state.passphrase)
    finally:
        clear_secret(state.passphrase)
        state.passphrase = None

    state.runner.run(
        [
            "zfs",
            "create",
            "-o",
            "encryption=aes-256-gcm",
            "-o",
            "keyformat=passphrase",
            "-o",
            f"keylocation=file://{KEY_FILE}",
            "-o",
            f"mountpoint={SECURE_MOUNTPOINT}",
            SECURE_DATASET,
        ]
    )


def configure_services(state: InstallationState) -> None:
    print("\nEnabling ZFS services...")
    state.runner.run(
        ["install", "-m", "0755", str(MOUNT_HELPER_SOURCE), str(MOUNT_HELPER_TARGET)]
    )
    state.runner.run(
        ["install", "-m", "0644", str(MOUNT_SERVICE_SOURCE), str(MOUNT_SERVICE_TARGET)]
    )
    state.runner.run(["systemctl", "daemon-reload"])
    state.runner.run(["systemctl", "enable", "--now", MOUNT_SERVICE_TARGET.name])
    state.runner.run(["systemctl", "enable", "--now", "zfs-zed.service"])
    scrub_timer = configure_monthly_scrub(state)
    validate_services(state, scrub_timer)


def configure_monthly_scrub(state: InstallationState) -> str:
    packaged_timer = f"zfs-scrub-monthly@{POOL_NAME}.timer"
    result = state.runner.capture(
        ["systemctl", "list-unit-files", "zfs-scrub-monthly@.timer", "--no-legend"],
        check=False,
    )
    if "zfs-scrub-monthly@.timer" in result.stdout:
        state.runner.run(["systemctl", "enable", "--now", packaged_timer])
        return packaged_timer

    state.runner.run(
        ["install", "-m", "0644", str(SCRUB_SERVICE_SOURCE), str(SCRUB_SERVICE_TARGET)]
    )
    state.runner.run(
        ["install", "-m", "0644", str(SCRUB_TIMER_SOURCE), str(SCRUB_TIMER_TARGET)]
    )
    state.runner.run(["systemctl", "daemon-reload"])
    state.runner.run(["systemctl", "enable", "--now", SCRUB_TIMER_TARGET.name])
    return SCRUB_TIMER_TARGET.name


def validate_services(state: InstallationState, scrub_timer: str) -> None:
    state.runner.run(["systemctl", "is-active", "--quiet", MOUNT_SERVICE_TARGET.name])
    state.runner.run(["systemctl", "is-enabled", "--quiet", scrub_timer])
    state.runner.run(["systemctl", "is-active", "--quiet", scrub_timer])
    if state.runner.capture(
        ["zfs", "get", "-H", "-o", "value", "mounted", SECURE_DATASET]
    ).stdout.strip() != "yes":
        raise InstallerError(f"Encrypted dataset is not mounted: {SECURE_DATASET}")


def show_result(state: InstallationState) -> None:
    print("\nZFS setup complete.\n")
    state.runner.run(["zpool", "status", "-v", POOL_NAME])
    print()
    state.runner.run(["zpool", "get", "ashift,autotrim", POOL_NAME])
    print()
    state.runner.run(
        [
            "zfs",
            "list",
            "-o",
            "name,used,avail,compression,encryption,mountpoint",
            POOL_NAME,
            SECURE_DATASET,
        ]
    )
    print(f"\nThe passphrase file is {KEY_FILE} with mode 0600.")
    print("If it is lost, recreate it with the exact passphrase and no trailing newline.")
    print(f"Then run: zfs load-key {SECURE_DATASET} && zfs mount {SECURE_DATASET}")


def main() -> int:
    state: InstallationState | None = None
    try:
        with open("/dev/tty", "r+", encoding="utf-8", buffering=1) as tty:
            state = InstallationState(
                tty=tty,
                runner=CommandRunner(),
            )
            try:
                run_installation(state)
            finally:
                clear_secret(state.passphrase)
                state.passphrase = None
    except KeyboardInterrupt:
        print("\nCancelled; no further changes will be made.", file=sys.stderr)
        report_partial_pool(state, POOL_NAME)
        return 130
    except EOFError:
        print("\nERROR: Terminal input ended unexpectedly", file=sys.stderr)
        report_partial_pool(state, POOL_NAME)
        return 1
    except InstallerError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        report_partial_pool(state, POOL_NAME)
        return 1
    except subprocess.CalledProcessError as error:
        print(
            f"\nERROR: Command failed with exit code {error.returncode}: "
            f"{shlex.join(error.cmd)}",
            file=sys.stderr,
        )
        report_partial_pool(state, POOL_NAME)
        return error.returncode or 1
    except OSError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        report_partial_pool(state, POOL_NAME)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
