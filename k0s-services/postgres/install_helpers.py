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
SECRET_NAME = "postgres-credentials"
DATASET_SUFFIX = "k0s/services-backed/postgres"


def load_config() -> PostgresConfig:
    root_dataset = os.environ.get("ROOT_DATASET", "tank/secure")
    volume_size = os.environ.get("POSTGRES_VOLUME_SIZE", "20G")
    max_ram = os.environ.get("POSTGRES_MAX_RAM", "")
    database = os.environ.get("POSTGRES_DB", "zabbix")
    username = os.environ.get("POSTGRES_USER", "zabbix")
    password = os.environ.get("POSTGRES_PASSWORD", "")

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
    for name, value in (("POSTGRES_DB", database), ("POSTGRES_USER", username)):
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", value):
            raise InstallerError(f"Invalid {name}: {value}")
    if not password:
        raise InstallerError("POSTGRES_PASSWORD must be set")

    return PostgresConfig(
        root_dataset=root_dataset,
        volume_size=volume_size,
        max_ram=max_ram,
        database=database,
        username=username,
        password=password,
        shared_buffers=half_memory(max_ram),
        shared_buffers_bytes=memory_bytes(half_memory(max_ram)),
    )


def memory_bytes(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)(Ki|Mi|Gi|Ti)", value)
    if match is None:
        raise InstallerError(f"Invalid memory size: {value}")
    multipliers = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
    return int(match.group(1)) * multipliers[match.group(2)]


def half_memory(value: str) -> str:
    match = re.fullmatch(r"([1-9][0-9]*)(Ki|Mi|Gi|Ti)", value)
    if match is None:
        raise InstallerError(f"Invalid memory size: {value}")

    number = int(match.group(1))
    multiplier = {"Ki": 1, "Mi": 1024, "Gi": 1024**2, "Ti": 1024**3}[match.group(2)]
    half_mebibytes = number * multiplier // 2 // 1024
    if half_mebibytes < 128:
        raise InstallerError("POSTGRES_MAX_RAM must produce at least 128Mi shared_buffers")
    return f"{half_mebibytes}Mi"


def dataset_spec(config: PostgresConfig, root_mountpoint: Path) -> DatasetSpec:
    return service_dataset_spec(config.root_dataset, root_mountpoint, DATASET_SUFFIX)


@dataclass(frozen=True)
class PostgresConfig:
    root_dataset: str
    volume_size: str
    max_ram: str
    database: str
    username: str
    password: str
    shared_buffers: str
    shared_buffers_bytes: int
