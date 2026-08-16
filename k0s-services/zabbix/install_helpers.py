from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import (  # noqa: E402
    CommandRunner,
    InstallerError,
    ZABBIX_HOSTNAME,
    require_commands,
    require_root,
)
from k0s_service_helpers import (  # noqa: E402
    DatasetSpec,
    ensure_service_dataset,
    service_dataset_spec,
)

DATASET_SUFFIX = "backup/k0s/services/zabbix"


def load_config() -> InstallConfig:
    root_dataset = os.environ.get("ROOT_DATASET", "tank/secure")
    storage_size = os.environ.get("ZABBIX_STORAGE_SIZE", "5G")
    node_port = os.environ.get("ZABBIX_SERVER_NODE_PORT", "31051")
    web_node_port = os.environ.get("ZABBIX_WEB_NODE_PORT", "30080")
    hostname = ZABBIX_HOSTNAME
    admin_username = os.environ.get("ZABBIX_ADMIN_USERNAME", "Admin")
    admin_password = os.environ.get("ZABBIX_ADMIN_PASSWORD", "")
    database = os.environ.get("ZABBIX_DB_NAME", "zabbix")
    database_username = os.environ.get("ZABBIX_DB_USER", "zabbix")
    database_password = os.environ.get("ZABBIX_DB_PASSWORD", "")

    if not re.fullmatch(r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)+", root_dataset):
        raise InstallerError(f"Invalid ROOT_DATASET: {root_dataset}")
    for name, value in (("ZABBIX_STORAGE_SIZE", storage_size),):
        if not re.fullmatch(r"[1-9][0-9]*[KMGTPE]", value):
            raise InstallerError(f"Invalid {name}: {value}")
    for name, value in (
        ("ZABBIX_SERVER_NODE_PORT", node_port),
        ("ZABBIX_WEB_NODE_PORT", web_node_port),
    ):
        if not value.isdecimal() or not 30000 <= int(value) <= 32767:
            raise InstallerError(f"{name} must be a Kubernetes NodePort")
    if node_port == web_node_port:
        raise InstallerError("Zabbix server and web NodePorts must differ")
    for name, value in (
        ("ZABBIX_HOSTNAME", hostname),
        ("ZABBIX_ADMIN_USERNAME", admin_username),
    ):
        if not value.strip() or "\n" in value or "\r" in value:
            raise InstallerError(f"Invalid {name}")
    if len(hostname) > 128:
        raise InstallerError("ZABBIX_HOSTNAME must not exceed 128 characters")
    if not admin_password:
        raise InstallerError("ZABBIX_ADMIN_PASSWORD must be set")
    for name, value in (
        ("ZABBIX_DB_NAME", database),
        ("ZABBIX_DB_USER", database_username),
    ):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise InstallerError(f"Invalid {name}: {value}")
    if database.lower() in {"postgres", "template0", "template1"}:
        raise InstallerError("ZABBIX_DB_NAME must not use a PostgreSQL system database")
    normalized_username = database_username.lower()
    if normalized_username == "postgres" or normalized_username.startswith("pg_"):
        raise InstallerError("ZABBIX_DB_USER must not use a PostgreSQL system role")

    if not database_password:
        raise InstallerError("ZABBIX_DB_PASSWORD must be set")

    return InstallConfig(
        root_dataset=root_dataset,
        storage_size=storage_size,
        server_node_port=int(node_port),
        web_node_port=int(web_node_port),
        hostname=hostname,
        admin_username=admin_username,
        admin_password=admin_password,
        database=database,
        database_username=database_username,
        database_password=database_password,
    )


def dataset_spec(config: InstallConfig, root_mountpoint: Path) -> DatasetSpec:
    return service_dataset_spec(config.root_dataset, root_mountpoint, DATASET_SUFFIX)


def ensure_zabbix_dataset(
    dataset: DatasetSpec,
    runner: CommandRunner,
    quota: str,
) -> None:
    ensure_service_dataset(
        runner,
        dataset,
        {
            "compression": "zstd",
            "atime": "off",
            "recordsize": "16K",
            "quota": quota,
        },
    )


@dataclass(frozen=True)
class InstallConfig:
    root_dataset: str
    storage_size: str
    server_node_port: int
    web_node_port: int
    hostname: str
    admin_username: str
    admin_password: str
    database: str
    database_username: str
    database_password: str
