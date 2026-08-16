from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import (  # noqa: E402
    CommandRunner,
    InstallerError,
    command_exists,
    require_commands,
    require_root,
    write_managed_file,
)


def load_config() -> InstallConfig:
    root_dataset = os.environ.get("ROOT_DATASET", "tank/secure")
    k0s_version = os.environ.get("K0S_VERSION", "v1.36.2+k0s.0")

    if not re.fullmatch(r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)+", root_dataset):
        raise InstallerError(f"Invalid ROOT_DATASET: {root_dataset}")
    if not k0s_version:
        raise InstallerError("K0S_VERSION cannot be empty")

    return InstallConfig(
        root_dataset=root_dataset,
        k0s_version=k0s_version,
    )


def ensure_dataset(runner: CommandRunner, spec: DatasetSpec) -> None:
    result = runner.run(
        ["zfs", "list", "-H", "-o", "name", spec.name],
        check=False,
    )
    if result.returncode == 0:
        current_mountpoint = zfs_value(runner, spec.name, "mountpoint")
        if current_mountpoint != str(spec.mountpoint):
            raise InstallerError(
                f"{spec.name} has mountpoint {current_mountpoint}; "
                f"expected {spec.mountpoint}"
            )
    else:
        runner.run(
            [
                "zfs",
                "create",
                "-o",
                f"mountpoint={spec.mountpoint}",
                "-o",
                "compression=zstd",
                "-o",
                "atime=off",
                "-o",
                "xattr=sa",
                "-o",
                "acltype=posixacl",
                spec.name,
            ]
        )

    if zfs_value(runner, spec.name, "mounted") != "yes":
        runner.run(["zfs", "mount", spec.name])


def zfs_value(runner: CommandRunner, dataset: str, property_name: str) -> str:
    result = runner.run(
        ["zfs", "get", "-H", "-o", "value", property_name, dataset]
    )
    return result.stdout.strip()


@dataclass(frozen=True)
class InstallConfig:
    root_dataset: str
    k0s_version: str


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    mountpoint: Path
