from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import (
    CommandRunner,
    InstallerError,
    require_commands,
    require_root,
)  # noqa: E402
from k0s_service_helpers import DatasetSpec, service_dataset_spec  # noqa: E402

NAMESPACE = "private-cloud"
SERVICE_NAME = "postgres"
SECRET_NAME = "postgres-admin-credentials"
ADMIN_DATABASE = "postgres"
ADMIN_USERNAME = "postgres"
DATASET_SUFFIX = "backup/k0s/services/postgres"


def load_config() -> PostgresConfig:
    root_dataset = os.environ.get("ROOT_DATASET", "tank/secure")
    volume_size = os.environ.get("POSTGRES_VOLUME_SIZE", "20G")
    max_ram = os.environ.get("POSTGRES_MAX_RAM", "")
    admin_password = os.environ.get("POSTGRES_ADMIN_PASSWORD", "")

    if not re.fullmatch(r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)+", root_dataset):
        raise InstallerError(f"Invalid ROOT_DATASET: {root_dataset}")
    if not re.fullmatch(r"[1-9][0-9]*[KMGTPE]", volume_size):
        raise InstallerError(
            "POSTGRES_VOLUME_SIZE must be a positive whole size such as 20G"
        )
    if not max_ram:
        raise InstallerError("POSTGRES_MAX_RAM must be set")
    if not re.fullmatch(r"[1-9][0-9]*(?:Ki|Mi|Gi|Ti)", max_ram):
        raise InstallerError(
            "POSTGRES_MAX_RAM must be a positive binary size such as 2Gi"
        )
    if not admin_password:
        raise InstallerError("POSTGRES_ADMIN_PASSWORD must be set")
    shared_buffers_mebibytes = half_memory_mebibytes(max_ram)

    return PostgresConfig(
        root_dataset=root_dataset,
        volume_size=volume_size,
        max_ram=max_ram,
        admin_password=admin_password,
        shared_buffers=f"{shared_buffers_mebibytes}MB",
        shared_buffers_bytes=shared_buffers_mebibytes * 1024**2,
    )


def half_memory_mebibytes(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)(Ki|Mi|Gi|Ti)", value)
    if match is None:
        raise InstallerError(f"Invalid memory size: {value}")

    number = int(match.group(1))
    multiplier = {"Ki": 1, "Mi": 1024, "Gi": 1024**2, "Ti": 1024**3}[match.group(2)]
    half_mebibytes = number * multiplier // 2 // 1024
    if half_mebibytes < 128:
        raise InstallerError("POSTGRES_MAX_RAM must produce at least 128Mi shared_buffers")
    return half_mebibytes


def dataset_spec(config: PostgresConfig, root_mountpoint: Path) -> DatasetSpec:
    return service_dataset_spec(config.root_dataset, root_mountpoint, DATASET_SUFFIX)


@dataclass(frozen=True)
class PostgresConfig:
    root_dataset: str
    volume_size: str
    max_ram: str
    admin_password: str
    shared_buffers: str
    shared_buffers_bytes: int
