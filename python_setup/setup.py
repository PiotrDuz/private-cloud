#!/usr/bin/env python3
from __future__ import annotations

import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from setup_helpers import (
    InstallerFailure,
    SetupCancelled,
    SetupError,
    begin_step,
    prompt_choice,
    prompt_secret,
    prompt_value,
    require_setup_environment,
    resolve_review,
    review_configuration,
    run_installer,
    validate_absolute_path,
    validate_dataset,
    validate_identifier,
    validate_memory,
    validate_node_port,
    validate_nonempty,
    validate_positive_integer,
    validate_server_address,
    validate_zfs_size,
)

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
ZFS_INSTALLER = PROJECT_DIRECTORY / "zfs" / "zfs-setup.py"
K0S_INSTALLER = PROJECT_DIRECTORY / "k0s" / "install.py"
POSTGRES_INSTALLER = PROJECT_DIRECTORY / "k0s-services" / "postgres" / "install.py"
ZABBIX_SERVICE_INSTALLER = PROJECT_DIRECTORY / "k0s-services" / "zabbix" / "install.py"
ZABBIX_AGENT_INSTALLER = PROJECT_DIRECTORY / "zabbix" / "install.py"
INSTALLERS = (
    ZFS_INSTALLER,
    K0S_INSTALLER,
    POSTGRES_INSTALLER,
    ZABBIX_SERVICE_INSTALLER,
    ZABBIX_AGENT_INSTALLER,
)
STEP_COUNT = len(INSTALLERS)


def main() -> int:
    try:
        require_setup_environment(INSTALLERS)
        context = SetupContext()
        print("Private cloud interactive setup")
        print("Stages run in dependency order and stop on the first failure.")
        context.results["zfs"] = run_zfs_step()
        context.results["k0s"] = run_k0s_step(context)
        context.results["postgres"] = run_postgres_step(context)
        context.results["zabbix_service"] = run_zabbix_service_step(context)
        context.results["zabbix_agent"] = run_zabbix_agent_step(context)
        show_result(context)
    except SetupCancelled:
        print("\nSetup cancelled.", file=sys.stderr)
        return 130
    except InstallerFailure as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return error.returncode or 1
    except (EOFError, SetupError) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSetup interrupted.", file=sys.stderr)
        return 130
    return 0


def run_zfs_step() -> str:
    if not begin_step(
        1,
        STEP_COUNT,
        "ZFS storage",
        "This installer selects and permanently erases at least three disks.",
    ):
        return "skipped"
    print("The ZFS installer will request disks, an encryption passphrase, and final confirmation.")
    run_installer("ZFS storage", ZFS_INSTALLER)
    return "completed"


def run_k0s_step(context: SetupContext) -> str:
    if not begin_step(
        2,
        STEP_COUNT,
        "k0s cluster",
        "This installer creates the k0s datasets, controller, and local volumes.",
    ):
        return "skipped"

    while True:
        root_dataset = prompt_value(
            "Encrypted root dataset",
            default=context.root_dataset,
            validator=validate_dataset,
        )
        version = prompt_value(
            "k0s version",
            default="v1.36.2+k0s.0",
            validator=validate_nonempty,
        )
        pv_count = prompt_value(
            "Generic persistent volume count",
            default="2",
            validator=validate_positive_integer,
        )
        pv_size = prompt_value(
            "Size of each generic persistent volume",
            default="5G",
            validator=validate_zfs_size,
        )
        decision = resolve_review(
            review_configuration(
                "k0s",
                (
                    ("Root dataset", root_dataset),
                    ("Version", version),
                    ("PV count", pv_count),
                    ("PV size", pv_size),
                ),
            )
        )
        if decision is None:
            continue
        if decision is False:
            return "skipped"
        break

    run_installer(
        "k0s cluster",
        K0S_INSTALLER,
        environment={
            "ROOT_DATASET": root_dataset,
            "K0S_VERSION": version,
            "PV_COUNT": pv_count,
            "PV_SIZE": pv_size,
        },
    )
    context.root_dataset = root_dataset
    return "completed"


def run_postgres_step(context: SetupContext) -> str:
    if not begin_step(
        3,
        STEP_COUNT,
        "PostgreSQL service",
        "This installer creates the tuned PostgreSQL dataset and Kubernetes service.",
    ):
        return "skipped"

    while True:
        root_dataset = prompt_value(
            "Encrypted root dataset",
            default=context.root_dataset,
            validator=validate_dataset,
        )
        volume_size = prompt_value(
            "PostgreSQL volume size",
            default="20G",
            validator=validate_zfs_size,
        )
        max_ram = prompt_value(
            "PostgreSQL maximum RAM",
            validator=validate_memory,
        )
        database = prompt_value(
            "PostgreSQL database",
            default="zabbix",
            validator=validate_identifier,
        )
        username = prompt_value(
            "PostgreSQL user",
            default="zabbix",
            validator=validate_identifier,
        )
        password = prompt_secret("PostgreSQL password")
        decision = resolve_review(
            review_configuration(
                "PostgreSQL",
                (
                    ("Root dataset", root_dataset),
                    ("Volume size", volume_size),
                    ("Maximum RAM", max_ram),
                    ("shared_buffers", "50% of maximum RAM"),
                    ("Database", database),
                    ("User", username),
                    ("Password", "provided"),
                ),
            )
        )
        if decision is None:
            password = ""
            continue
        if decision is False:
            password = ""
            return "skipped"
        break

    try:
        run_installer(
            "PostgreSQL service",
            POSTGRES_INSTALLER,
            environment={
                "ROOT_DATASET": root_dataset,
                "POSTGRES_VOLUME_SIZE": volume_size,
                "POSTGRES_MAX_RAM": max_ram,
                "POSTGRES_DB": database,
                "POSTGRES_USER": username,
                "POSTGRES_PASSWORD": password,
            },
        )
    finally:
        password = ""
    context.root_dataset = root_dataset
    return "completed"


def run_zabbix_service_step(context: SetupContext) -> str:
    if not begin_step(
        4,
        STEP_COUNT,
        "Zabbix Kubernetes service",
        "This installer deploys Zabbix Server and its web frontend.",
    ):
        return "skipped"

    while True:
        root_dataset = prompt_value(
            "Encrypted root dataset",
            default=context.root_dataset,
            validator=validate_dataset,
        )
        storage_size = prompt_value(
            "Zabbix volume size",
            default="5G",
            validator=validate_zfs_size,
        )
        server_node_port = prompt_value(
            "Zabbix Server NodePort",
            default=context.server_node_port,
            validator=validate_node_port,
        )
        web_node_port = prompt_value(
            "Zabbix web NodePort",
            default=context.web_node_port,
            validator=validate_node_port,
        )
        if server_node_port == web_node_port:
            print("The server and web NodePorts must differ", file=sys.stderr)
            continue
        decision = resolve_review(
            review_configuration(
                "Zabbix service",
                (
                    ("Root dataset", root_dataset),
                    ("Volume size", storage_size),
                    ("Server NodePort", server_node_port),
                    ("Web NodePort", web_node_port),
                ),
            )
        )
        if decision is None:
            continue
        if decision is False:
            return "skipped"
        break

    run_installer(
        "Zabbix Kubernetes service",
        ZABBIX_SERVICE_INSTALLER,
        environment={
            "ROOT_DATASET": root_dataset,
            "ZABBIX_STORAGE_SIZE": storage_size,
            "ZABBIX_SERVER_NODE_PORT": server_node_port,
            "ZABBIX_WEB_NODE_PORT": web_node_port,
        },
    )
    context.root_dataset = root_dataset
    context.server_node_port = server_node_port
    context.web_node_port = web_node_port
    return "completed"


def run_zabbix_agent_step(context: SetupContext) -> str:
    if not begin_step(
        5,
        STEP_COUNT,
        "Zabbix host agent",
        "This installer configures host, ZFS, and SMART monitoring.",
    ):
        return "skipped"

    while True:
        hostname = prompt_value(
            "Zabbix host name",
            default=socket.gethostname(),
            validator=validate_nonempty,
        )
        server_active = prompt_value(
            "Zabbix Server address",
            default=f"{socket.gethostname()}:{context.server_node_port}",
            validator=validate_server_address,
        )
        transport = prompt_choice(
            "Agent transport",
            {"p": "psk", "psk": "psk", "t": "plaintext", "plaintext": "plaintext"},
            "psk",
        )
        psk_identity = ""
        psk_file = ""
        if transport == "psk":
            psk_identity = prompt_value(
                "PSK identity",
                default=f"{hostname}-zabbix",
                validator=validate_nonempty,
            )
            psk_file = prompt_value(
                "PSK file",
                default="/etc/zabbix/zabbix_agent2.psk",
                validator=validate_absolute_path,
            )
        values = [
            ("Host name", hostname),
            ("Server", server_active),
            ("Transport", transport),
        ]
        if transport == "psk":
            values.extend((("PSK identity", psk_identity), ("PSK file", psk_file)))
        decision = resolve_review(review_configuration("Zabbix host agent", values))
        if decision is None:
            continue
        if decision is False:
            return "skipped"
        break

    arguments = ["--server-active", server_active, "--hostname", hostname]
    if transport == "psk":
        arguments.extend(("--psk-identity", psk_identity, "--psk-file", psk_file))
    else:
        arguments.append("--allow-plaintext")
    run_installer(
        "Zabbix host agent",
        ZABBIX_AGENT_INSTALLER,
        arguments=arguments,
    )
    return "completed"


def show_result(context: SetupContext) -> None:
    print("\nSetup flow finished:")
    for name, status in context.results.items():
        print(f"  {name}: {status}")
    print(f"  Zabbix Server: <node-address>:{context.server_node_port}")
    print(f"  Zabbix web: http://<node-address>:{context.web_node_port}")


@dataclass
class SetupContext:
    root_dataset: str = "tank/secure"
    server_node_port: str = "31051"
    web_node_port: str = "30080"
    results: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = {}


if __name__ == "__main__":
    raise SystemExit(main())
