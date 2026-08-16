#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from setup_helpers import (
    InstallerFailure,
    SetupCancelled,
    SetupError,
    SetupProgress,
    ZABBIX_HOSTNAME,
    begin_step,
    load_setup_progress,
    prompt_choice,
    prompt_secret,
    prompt_value,
    require_setup_environment,
    resolve_review,
    review_configuration,
    run_installer,
    save_setup_progress,
    validate_identifier,
    validate_memory,
    validate_node_port,
    validate_nonempty,
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
STAGE_NAMES = ("zfs", "k0s", "postgres", "zabbix_service", "zabbix_agent")
STAGE_TITLES = {
    "zfs": "ZFS storage",
    "k0s": "k0s cluster",
    "postgres": "PostgreSQL service",
    "zabbix_service": "Zabbix Kubernetes service",
    "zabbix_agent": "Zabbix host agent",
}
STEP_COUNT = len(STAGE_NAMES)
PROGRESS_FILE = Path("/var/lib/private-cloud/setup-progress.json")
ROOT_DATASET = "tank/secure"


def main() -> int:
    try:
        require_setup_environment(INSTALLERS)
        context = SetupContext()
        print("Private cloud interactive setup")
        print("Stages run in dependency order and stop on the first failure.")
        progress = prepare_progress(context)
        run_checkpointed_stage(context, progress, "zfs", run_zfs_step)
        run_checkpointed_stage(
            context,
            progress,
            "k0s",
            lambda: run_k0s_step(context),
        )
        run_checkpointed_stage(
            context,
            progress,
            "postgres",
            lambda: run_postgres_step(context),
        )
        run_checkpointed_stage(
            context,
            progress,
            "zabbix_service",
            lambda: run_zabbix_service_step(context),
        )
        run_checkpointed_stage(
            context,
            progress,
            "zabbix_agent",
            lambda: run_zabbix_agent_step(context),
        )
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


def prepare_progress(context: SetupContext) -> SetupProgress:
    try:
        progress = load_setup_progress(PROGRESS_FILE, STAGE_NAMES)
    except SetupError as error:
        print(f"WARNING: {error}", file=sys.stderr)
        action = prompt_choice(
            "Invalid saved progress",
            {"r": "reset", "reset": "reset", "q": "quit", "quit": "quit"},
            "reset",
        )
        if action == "quit":
            raise SetupCancelled
        progress = SetupProgress()

    if progress.completed or progress.current_stage is not None:
        show_saved_progress(progress)
        action = prompt_choice(
            "Saved progress",
            {
                "r": "resume",
                "resume": "resume",
                "x": "reset",
                "reset": "reset",
                "q": "quit",
                "quit": "quit",
            },
            "resume",
        )
        if action == "quit":
            raise SetupCancelled
        if action == "reset":
            progress = SetupProgress()
        else:
            restore_context(context, progress.context)

    progress.context = context_values(context)
    save_setup_progress(PROGRESS_FILE, progress)
    return progress


def run_checkpointed_stage(
    context: SetupContext,
    progress: SetupProgress,
    stage: str,
    installer: Callable[[], str],
) -> None:
    if stage in progress.completed:
        print(f"\nCheckpoint: {STAGE_TITLES[stage]} already completed.")
        context.results[stage] = "completed (saved)"
        return

    progress.current_stage = stage
    progress.context = context_values(context)
    save_setup_progress(PROGRESS_FILE, progress)
    result = installer()
    context.results[stage] = result
    progress.current_stage = None
    if result == "completed":
        progress.completed.append(stage)
    progress.context = context_values(context)
    save_setup_progress(PROGRESS_FILE, progress)


def show_saved_progress(progress: SetupProgress) -> None:
    print(f"\nSaved progress: {PROGRESS_FILE}")
    if progress.completed:
        titles = ", ".join(STAGE_TITLES[stage] for stage in progress.completed)
        print(f"  Completed: {titles}")
    if progress.current_stage is not None:
        print(f"  Interrupted at: {STAGE_TITLES[progress.current_stage]}")
    next_stage = next(
        (stage for stage in STAGE_NAMES if stage not in progress.completed),
        None,
    )
    if next_stage is not None:
        print(f"  Resume from: {STAGE_TITLES[next_stage]}")
    else:
        print("  All stages completed.")


def context_values(context: SetupContext) -> dict[str, str]:
    return {
        "k0s_config_quota": context.k0s_config_quota,
        "k0s_images_quota": context.k0s_images_quota,
        "k0s_ephemeral_quota": context.k0s_ephemeral_quota,
        "server_node_port": context.server_node_port,
        "web_node_port": context.web_node_port,
    }


def restore_context(context: SetupContext, values: dict[str, str]) -> None:
    for name in (
        "k0s_config_quota",
        "k0s_images_quota",
        "k0s_ephemeral_quota",
        "server_node_port",
        "web_node_port",
    ):
        if name in values:
            setattr(context, name, values[name])


def run_zfs_step() -> str:
    if not begin_step(
        1,
        STEP_COUNT,
        "ZFS storage",
        "This installer selects and permanently erases at least two disks.",
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
        "This installer creates the fixed k0s datasets and controller.",
    ):
        return "skipped"

    while True:
        config_quota = prompt_value(
            "k0s configuration dataset quota",
            default=context.k0s_config_quota,
            validator=validate_zfs_size,
        )
        images_quota = prompt_value(
            "k0s images dataset quota",
            default=context.k0s_images_quota,
            validator=validate_zfs_size,
        )
        ephemeral_quota = prompt_value(
            "k0s ephemeral dataset quota",
            default=context.k0s_ephemeral_quota,
            validator=validate_zfs_size,
        )
        decision = resolve_review(
            review_configuration(
                "k0s storage",
                (
                    ("Root dataset", ROOT_DATASET),
                    ("Configuration quota", config_quota),
                    ("Images quota", images_quota),
                    ("Ephemeral quota", ephemeral_quota),
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
            "ROOT_DATASET": ROOT_DATASET,
            "K0S_CONFIG_QUOTA": config_quota,
            "K0S_IMAGES_QUOTA": images_quota,
            "K0S_EPHEMERAL_QUOTA": ephemeral_quota,
        },
    )
    context.k0s_config_quota = config_quota
    context.k0s_images_quota = images_quota
    context.k0s_ephemeral_quota = ephemeral_quota
    return "completed"


def run_postgres_step(context: SetupContext) -> str:
    if not begin_step(
        3,
        STEP_COUNT,
        "PostgreSQL service",
        "This installer creates the tuned PostgreSQL server and administrator.",
    ):
        return "skipped"

    while True:
        volume_size = prompt_value(
            "PostgreSQL volume size",
            default="20G",
            validator=validate_zfs_size,
        )
        max_ram = prompt_value(
            "PostgreSQL maximum RAM",
            validator=validate_memory,
        )
        admin_password = prompt_secret("PostgreSQL administrator password")
        decision = resolve_review(
            review_configuration(
                "PostgreSQL",
                (
                    ("Root dataset", ROOT_DATASET),
                    ("Volume size", volume_size),
                    ("Maximum RAM", max_ram),
                    ("shared_buffers", "50% of maximum RAM"),
                    ("Administrator database", "postgres"),
                    ("Administrator user", "postgres"),
                    ("Administrator password", "provided"),
                ),
            )
        )
        if decision is None:
            admin_password = ""
            continue
        if decision is False:
            admin_password = ""
            return "skipped"
        break

    try:
        run_installer(
            "PostgreSQL service",
            POSTGRES_INSTALLER,
            environment={
                "ROOT_DATASET": ROOT_DATASET,
                "POSTGRES_VOLUME_SIZE": volume_size,
                "POSTGRES_MAX_RAM": max_ram,
                "POSTGRES_ADMIN_PASSWORD": admin_password,
            },
        )
    finally:
        admin_password = ""
    return "completed"

def run_zabbix_service_step(context: SetupContext) -> str:
    if not begin_step(
        4,
        STEP_COUNT,
        "Zabbix Kubernetes service",
        "This installer creates the database, deploys Zabbix, and registers the host.",
    ):
        return "skipped"

    while True:
        storage_size = prompt_value(
            "Zabbix volume size",
            default="5G",
            validator=validate_zfs_size,
        )
        database = prompt_value(
            "Zabbix database",
            default="zabbix",
            validator=validate_identifier,
        )
        database_username = prompt_value(
            "Zabbix database user",
            default="zabbix",
            validator=validate_identifier,
        )
        database_password = prompt_secret("Zabbix database password")
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
            database_password = ""
            print("The server and web NodePorts must differ", file=sys.stderr)
            continue
        admin_username = prompt_value(
            "Zabbix administrator user",
            default="Admin",
            validator=validate_nonempty,
        )
        admin_password = prompt_secret(
            "Zabbix administrator password",
            confirm=False,
        )
        decision = resolve_review(
            review_configuration(
                "Zabbix service",
                (
                    ("Root dataset", ROOT_DATASET),
                    ("Volume size", storage_size),
                    ("Database", database),
                    ("Database user", database_username),
                    ("Database password", "provided"),
                    ("Server NodePort", server_node_port),
                    ("Web NodePort", web_node_port),
                    ("Host name", ZABBIX_HOSTNAME),
                    ("Administrator", admin_username),
                    ("Administrator password", "provided"),
                    ("Agent transport", "plaintext over localhost"),
                ),
            )
        )
        if decision is None:
            database_password = ""
            admin_password = ""
            continue
        if decision is False:
            database_password = ""
            admin_password = ""
            return "skipped"
        break

    try:
        run_installer(
            "Zabbix Kubernetes service",
            ZABBIX_SERVICE_INSTALLER,
            environment={
                "ROOT_DATASET": ROOT_DATASET,
                "ZABBIX_STORAGE_SIZE": storage_size,
                "ZABBIX_DB_NAME": database,
                "ZABBIX_DB_USER": database_username,
                "ZABBIX_DB_PASSWORD": database_password,
                "ZABBIX_SERVER_NODE_PORT": server_node_port,
                "ZABBIX_WEB_NODE_PORT": web_node_port,
                "ZABBIX_HOSTNAME": ZABBIX_HOSTNAME,
                "ZABBIX_ADMIN_USERNAME": admin_username,
                "ZABBIX_ADMIN_PASSWORD": admin_password,
            },
        )
    finally:
        database_password = ""
        admin_password = ""
    context.server_node_port = server_node_port
    context.web_node_port = web_node_port
    return "completed"

def run_zabbix_agent_step(context: SetupContext) -> str:
    if not begin_step(
        5,
        STEP_COUNT,
        "Zabbix host agent",
        "This installer configures host, ZFS, SMART, and ECC monitoring.",
    ):
        return "skipped"

    while True:
        server_active = prompt_value(
            "Zabbix Server address",
            default=f"127.0.0.1:{context.server_node_port}",
            validator=validate_server_address,
        )
        decision = resolve_review(
            review_configuration(
                "Zabbix host agent",
                (
                    ("Host name", ZABBIX_HOSTNAME),
                    ("Server", server_active),
                    ("Transport", "plaintext"),
                ),
            )
        )
        if decision is None:
            continue
        if decision is False:
            return "skipped"
        break

    run_installer(
        "Zabbix host agent",
        ZABBIX_AGENT_INSTALLER,
        arguments=("--server-active", server_active),
    )
    return "completed"


def show_result(context: SetupContext) -> None:
    print("\nSetup flow finished:")
    for name, status in context.results.items():
        print(f"  {name}: {status}")
    print(f"  Zabbix Server: <node-address>:{context.server_node_port}")
    print(f"  Zabbix web: http://<node-address>:{context.web_node_port}")
    print(f"  Progress: {PROGRESS_FILE}")


@dataclass
class SetupContext:
    k0s_config_quota: str = "1G"
    k0s_images_quota: str = "10G"
    k0s_ephemeral_quota: str = "10G"
    server_node_port: str = "31051"
    web_node_port: str = "30080"
    results: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = {}


if __name__ == "__main__":
    raise SystemExit(main())
