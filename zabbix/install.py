#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from install_helpers import (
    CommandRunner,
    InstallConfig,
    ZABBIX_HOSTNAME,
    InstallerError,
    read_os_release,
    require_commands,
    require_root,
    write_managed_file,
)

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
ZFS_COLLECTOR_SOURCE = SCRIPT_DIRECTORY / "zabbix-zfs-collector.py"
ZFS_TEMPLATE_SOURCE = SCRIPT_DIRECTORY / "zabbix-zfs-template.yaml"
ECC_COLLECTOR_SOURCE = SCRIPT_DIRECTORY / "zabbix-memory-ecc-collector.py"
ECC_TEMPLATE_SOURCE = SCRIPT_DIRECTORY / "zabbix-memory-ecc-template.yaml"
SMART_WRAPPER_SOURCE = SCRIPT_DIRECTORY / "zabbix-smartctl-wrapper"
ZFS_COLLECTOR_TARGET = Path("/usr/local/libexec/zabbix/zfs-collector.py")
ECC_COLLECTOR_TARGET = Path("/usr/local/libexec/zabbix/memory-ecc-collector.py")
SMART_WRAPPER_TARGET = Path("/usr/local/libexec/zabbix/smartctl-wrapper")
AGENT_CONFIG = Path("/etc/zabbix/zabbix_agent2.conf")
ZFS_USERPARAM_CONFIG = Path("/etc/zabbix/zabbix_agent2.d/zfs.conf")
ECC_USERPARAM_CONFIG = Path("/etc/zabbix/zabbix_agent2.d/memory-ecc.conf")
SMART_PLUGIN_CONFIG = Path("/etc/zabbix/zabbix_agent2.d/plugins.d/smart.conf")
SMART_SUDOERS_CONFIG = Path("/etc/sudoers.d/zabbix-smartctl")
MANAGED_START = "# BEGIN PRIVATE-CLOUD ZABBIX SETTINGS"
MANAGED_END = "# END PRIVATE-CLOUD ZABBIX SETTINGS"
APT_LOCK_TIMEOUT_SECONDS = 600


def main() -> int:
    try:
        config = load_config()
        result = run_installation(config, CommandRunner())
    except InstallerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


def run_installation(
    config: InstallConfig,
    runner: CommandRunner,
) -> dict[str, Any]:
    preflight()
    install_packages(runner)
    load_memory_ecc_driver(runner)
    install_monitoring_assets(runner)
    configure_agent(config)
    validation = validate_installation(runner)
    runner.run(["systemctl", "enable", "--now", "zabbix-agent2.service"])
    runner.run(["systemctl", "restart", "zabbix-agent2.service"])
    runner.run(["systemctl", "is-active", "--quiet", "zabbix-agent2.service"])
    return installation_result(config, validation)


def load_config() -> InstallConfig:
    parser = argparse.ArgumentParser(description="Install the Zabbix host integration.")
    parser.add_argument("--server-active", required=True)
    args = parser.parse_args()

    for name, value in (("server-active", args.server_active),):
        if "\n" in value or "\r" in value:
            raise InstallerError(f"Invalid {name}")
    if not re.fullmatch(r"[^\s,]+(?::\d{1,5})?", args.server_active):
        raise InstallerError("Invalid server-active address")
    return InstallConfig(
        server_active=args.server_active,
        hostname=ZABBIX_HOSTNAME,
    )


def preflight() -> None:
    require_root()
    require_commands(["apt-get", "modprobe", "runuser", "systemctl"])
    distribution = read_os_release().get("ID", "")
    if distribution != "ubuntu":
        raise InstallerError(
            f"Only Ubuntu is supported; detected {distribution or 'unknown'}"
        )
    for source in (
        ZFS_COLLECTOR_SOURCE,
        ZFS_TEMPLATE_SOURCE,
        ECC_COLLECTOR_SOURCE,
        ECC_TEMPLATE_SOURCE,
        SMART_WRAPPER_SOURCE,
    ):
        if not source.is_file():
            raise InstallerError(f"Required Zabbix asset not found: {source}")


def install_packages(runner: CommandRunner) -> None:
    runner.run(
        [
            "apt-get",
            "-o",
            f"DPkg::Lock::Timeout={APT_LOCK_TIMEOUT_SECONDS}",
            "update",
        ]
    )
    environment = os.environ.copy()
    environment["DEBIAN_FRONTEND"] = "noninteractive"
    runner.run(
        [
            "apt-get",
            "-o",
            f"DPkg::Lock::Timeout={APT_LOCK_TIMEOUT_SECONDS}",
            "install",
            "-y",
            "zabbix-agent2",
            "python3",
            "smartmontools",
            "sudo",
        ],
        env=environment,
    )
    require_commands(["smartctl", "visudo", "zabbix_agent2"])


def load_memory_ecc_driver(runner: CommandRunner) -> None:
    runner.run(["modprobe", "igen6_edac"], check=False)


def install_monitoring_assets(runner: CommandRunner) -> None:
    write_managed_file(
        ZFS_COLLECTOR_TARGET,
        ZFS_COLLECTOR_SOURCE.read_text(encoding="utf-8"),
        0o755,
    )
    write_managed_file(
        ECC_COLLECTOR_TARGET,
        ECC_COLLECTOR_SOURCE.read_text(encoding="utf-8"),
        0o755,
    )
    write_managed_file(
        SMART_WRAPPER_TARGET,
        SMART_WRAPPER_SOURCE.read_text(encoding="utf-8"),
        0o755,
    )
    write_managed_file(
        ZFS_USERPARAM_CONFIG,
        render_zfs_user_parameters(),
        0o644,
    )
    write_managed_file(
        ECC_USERPARAM_CONFIG,
        render_ecc_user_parameters(),
        0o644,
    )
    write_managed_file(
        SMART_PLUGIN_CONFIG,
        render_smart_plugin_config(),
        0o644,
    )
    install_smart_permissions(runner)


def install_smart_permissions(runner: CommandRunner) -> None:
    content = render_smart_sudoers()
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="zabbix-smartctl-",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)
        temporary_path.chmod(0o440)
        runner.run(["visudo", "-cf", str(temporary_path)])
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    write_managed_file(SMART_SUDOERS_CONFIG, content, 0o440)


def configure_agent(config: InstallConfig) -> None:
    if not AGENT_CONFIG.is_file():
        raise InstallerError(f"Agent 2 configuration not found: {AGENT_CONFIG}")
    backup = AGENT_CONFIG.with_name(f"{AGENT_CONFIG.name}.pre-private-cloud")
    if not backup.exists():
        shutil.copy2(AGENT_CONFIG, backup)

    content = remove_managed_agent_settings(
        AGENT_CONFIG.read_text(encoding="utf-8")
    )
    include = "Include=/etc/zabbix/zabbix_agent2.d/*.conf"
    if include not in content.splitlines():
        content = f"{content.rstrip()}\n\n{include}\n"
    content = f"{content.rstrip()}\n\n{render_agent_settings(config)}"
    write_managed_file(AGENT_CONFIG, content, 0o644)


def remove_managed_agent_settings(content: str) -> str:
    setting = re.compile(
        r"^\s*(Server|ServerActive|Hostname|ListenIP|Timeout|TLSConnect|"
        r"TLSAccept|TLSPSKIdentity|TLSPSKFile)="
    )
    kept: list[str] = []
    managed = False
    for line in content.splitlines():
        if line == MANAGED_START:
            managed = True
            continue
        if line == MANAGED_END:
            managed = False
            continue
        if not managed and not setting.match(line):
            kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def validate_installation(runner: CommandRunner) -> dict[str, Any]:
    for mode in ("metrics", "snapshots"):
        result = runner.run(
            ["runuser", "-u", "zabbix", "--", str(ZFS_COLLECTOR_TARGET), mode]
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise InstallerError(f"The {mode} collector returned invalid JSON") from error
        if payload.get("error_count"):
            detail = "; ".join(payload.get("errors", []))
            raise InstallerError(f"The {mode} collector failed: {detail}")

    runner.run(["zabbix_agent2", "-t", "zfs.metrics", "-c", str(AGENT_CONFIG)])

    ecc_result = runner.run(
        ["runuser", "-u", "zabbix", "--", str(ECC_COLLECTOR_TARGET)]
    )
    try:
        ecc_payload = json.loads(ecc_result.stdout)
    except json.JSONDecodeError as error:
        raise InstallerError(
            "The memory ECC collector returned invalid JSON"
        ) from error
    if ecc_payload.get("error_count"):
        detail = "; ".join(ecc_payload.get("errors", []))
        raise InstallerError(f"The memory ECC collector failed: {detail}")
    runner.run(
        ["zabbix_agent2", "-t", "memory.ecc.metrics", "-c", str(AGENT_CONFIG)]
    )

    runner.run(
        ["runuser", "-u", "zabbix", "--", "sudo", "-n", str(SMART_WRAPPER_TARGET), "-j", "-V"]
    )
    discovery = runner.run(
        [
            "runuser",
            "-u",
            "zabbix",
            "--",
            "zabbix_agent2",
            "-t",
            "smart.disk.discovery",
            "-c",
            str(AGENT_CONFIG),
        ]
    ).stdout
    if "ZBX_NOTSUPPORTED" in discovery:
        raise InstallerError(f"SMART plugin validation failed: {discovery.strip()}")
    return {
        "memory_ecc_available": bool(ecc_payload.get("available")),
        "smart_disks_discovered": "[s|[]]" not in discovery,
    }


def installation_result(
    config: InstallConfig,
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "hostname": config.hostname,
        "memory_ecc_available": validation["memory_ecc_available"],
        "server_active": config.server_active,
        "smart_disks_discovered": validation["smart_disks_discovered"],
        "status": "installed",
        "ecc_template": str(ECC_TEMPLATE_SOURCE),
        "template": str(ZFS_TEMPLATE_SOURCE),
        "transport": "plaintext",
    }


def render_zfs_user_parameters() -> str:
    return (
        "# Managed by private-cloud/zabbix/install.py.\n"
        f"UserParameter=zfs.metrics,{ZFS_COLLECTOR_TARGET} metrics\n"
        f"UserParameter=zfs.snapshots,{ZFS_COLLECTOR_TARGET} snapshots\n"
    )


def render_ecc_user_parameters() -> str:
    return (
        "# Managed by private-cloud/zabbix/install.py.\n"
        f"UserParameter=memory.ecc.metrics,{ECC_COLLECTOR_TARGET}\n"
    )


def render_smart_plugin_config() -> str:
    return (
        "# Managed by private-cloud/zabbix/install.py.\n"
        f"Plugins.Smart.Path={SMART_WRAPPER_TARGET}\n"
    )


def render_smart_sudoers() -> str:
    return (
        "# Managed by private-cloud/zabbix/install.py.\n"
        "zabbix ALL=(root) NOPASSWD: "
        f"{SMART_WRAPPER_TARGET} -a *, "
        f"{SMART_WRAPPER_TARGET} --scan *, "
        f"{SMART_WRAPPER_TARGET} -j -V\n"
    )


def render_agent_settings(config: InstallConfig) -> str:
    lines = [
        MANAGED_START,
        "Server=127.0.0.1",
        f"ServerActive={config.server_active}",
        f"Hostname={config.hostname}",
        "ListenIP=127.0.0.1",
        "Timeout=30",
        "TLSConnect=unencrypted",
        "TLSAccept=unencrypted",
        MANAGED_END,
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
