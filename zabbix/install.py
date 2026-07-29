#!/usr/bin/env python3
from __future__ import annotations

import argparse
import grp
import json
import os
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from install_helpers import (
    CommandRunner,
    InstallConfig,
    InstallerError,
    read_os_release,
    require_commands,
    require_root,
    write_managed_file,
)

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
COLLECTOR_SOURCE = SCRIPT_DIRECTORY / "zabbix-zfs-collector.py"
TEMPLATE_SOURCE = SCRIPT_DIRECTORY / "zabbix-zfs-template.yaml"
SMART_WRAPPER_SOURCE = SCRIPT_DIRECTORY / "zabbix-smartctl-wrapper"
COLLECTOR_TARGET = Path("/usr/local/libexec/zabbix/zfs-collector.py")
SMART_WRAPPER_TARGET = Path("/usr/local/libexec/zabbix/smartctl-wrapper")
AGENT_CONFIG = Path("/etc/zabbix/zabbix_agent2.conf")
USERPARAM_CONFIG = Path("/etc/zabbix/zabbix_agent2.d/zfs.conf")
SMART_PLUGIN_CONFIG = Path("/etc/zabbix/zabbix_agent2.d/plugins.d/smart.conf")
SMART_SUDOERS_CONFIG = Path("/etc/sudoers.d/zabbix-smartctl")
MANAGED_START = "# BEGIN PRIVATE-CLOUD ZABBIX SETTINGS"
MANAGED_END = "# END PRIVATE-CLOUD ZABBIX SETTINGS"


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
    install_monitoring_assets(runner)
    configure_transport(config)
    configure_agent(config)
    validation = validate_installation(runner)
    runner.run(["systemctl", "enable", "--now", "zabbix-agent2.service"])
    runner.run(["systemctl", "restart", "zabbix-agent2.service"])
    runner.run(["systemctl", "is-active", "--quiet", "zabbix-agent2.service"])
    return installation_result(config, validation)


def load_config() -> InstallConfig:
    parser = argparse.ArgumentParser(description="Install the Zabbix host integration.")
    parser.add_argument("--server-active", required=True)
    parser.add_argument("--hostname", required=True)
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument("--psk-identity")
    transport.add_argument("--allow-plaintext", action="store_true")
    parser.add_argument(
        "--psk-file",
        type=Path,
        default=Path("/etc/zabbix/zabbix_agent2.psk"),
    )
    args = parser.parse_args()

    for name, value in (
        ("server-active", args.server_active),
        ("hostname", args.hostname),
        ("psk-identity", args.psk_identity or ""),
    ):
        if "\n" in value or "\r" in value:
            raise InstallerError(f"Invalid {name}")
    if not re.fullmatch(r"[^\s,]+(?::\d{1,5})?", args.server_active):
        raise InstallerError("Invalid server-active address")
    if not args.hostname.strip():
        raise InstallerError("Hostname cannot be empty")
    if args.psk_identity is not None and not args.psk_identity.strip():
        raise InstallerError("PSK identity cannot be empty")
    if not args.psk_file.is_absolute():
        raise InstallerError("PSK file must use an absolute path")

    return InstallConfig(
        server_active=args.server_active,
        hostname=args.hostname,
        psk_identity=args.psk_identity,
        psk_file=args.psk_file,
        allow_plaintext=args.allow_plaintext,
    )


def preflight() -> None:
    require_root()
    require_commands(["apt-get", "runuser", "systemctl"])
    distribution = read_os_release().get("ID", "")
    if distribution != "ubuntu":
        raise InstallerError(
            f"Only Ubuntu is supported; detected {distribution or 'unknown'}"
        )
    for source in (COLLECTOR_SOURCE, TEMPLATE_SOURCE, SMART_WRAPPER_SOURCE):
        if not source.is_file():
            raise InstallerError(f"Required Zabbix asset not found: {source}")


def install_packages(runner: CommandRunner) -> None:
    runner.run(["apt-get", "update"])
    environment = os.environ.copy()
    environment["DEBIAN_FRONTEND"] = "noninteractive"
    runner.run(
        [
            "apt-get",
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


def install_monitoring_assets(runner: CommandRunner) -> None:
    write_managed_file(
        COLLECTOR_TARGET,
        COLLECTOR_SOURCE.read_text(encoding="utf-8"),
        0o755,
    )
    write_managed_file(
        SMART_WRAPPER_TARGET,
        SMART_WRAPPER_SOURCE.read_text(encoding="utf-8"),
        0o755,
    )
    write_managed_file(
        USERPARAM_CONFIG,
        render_user_parameters(),
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


def configure_transport(config: InstallConfig) -> None:
    if config.allow_plaintext:
        return
    ensure_psk(config.psk_file)


def ensure_psk(path: Path) -> None:
    zabbix_gid = grp.getgrnam("zabbix").gr_gid
    if path.is_symlink():
        raise InstallerError(f"PSK path must not be a symbolic link: {path}")
    if not path.exists():
        if not path.parent.exists():
            path.parent.mkdir(parents=True, mode=0o750)
            os.chown(path.parent, 0, zabbix_gid)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as psk_file:
            psk_file.write(secrets.token_hex(32))

    if not path.is_file():
        raise InstallerError(f"PSK path must be a regular file: {path}")
    directory_stat = path.parent.stat()
    if directory_stat.st_uid != 0 or directory_stat.st_mode & 0o022:
        raise InstallerError(
            f"PSK directory must be root-owned and not group/world writable: {path.parent}"
        )
    psk_value = path.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", psk_value):
        raise InstallerError("PSK file must contain exactly 64 hexadecimal characters")
    os.chown(path, 0, zabbix_gid)
    path.chmod(0o640)


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
            ["runuser", "-u", "zabbix", "--", str(COLLECTOR_TARGET), mode]
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise InstallerError(f"The {mode} collector returned invalid JSON") from error
        if payload.get("error_count"):
            detail = "; ".join(payload.get("errors", []))
            raise InstallerError(f"The {mode} collector failed: {detail}")

    runner.run(["zabbix_agent2", "-t", "zfs.metrics", "-c", str(AGENT_CONFIG)])
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
    return {"smart_disks_discovered": "[s|[]]" not in discovery}


def installation_result(
    config: InstallConfig,
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "hostname": config.hostname,
        "server_active": config.server_active,
        "smart_disks_discovered": validation["smart_disks_discovered"],
        "status": "installed",
        "template": str(TEMPLATE_SOURCE),
        "transport": "plaintext" if config.allow_plaintext else "psk",
    }


def render_user_parameters() -> str:
    return (
        "# Managed by private-cloud/zabbix/install.py.\n"
        f"UserParameter=zfs.metrics,{COLLECTOR_TARGET} metrics\n"
        f"UserParameter=zfs.snapshots,{COLLECTOR_TARGET} snapshots\n"
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
    ]
    if config.allow_plaintext:
        lines.extend(["TLSConnect=unencrypted", "TLSAccept=unencrypted"])
    else:
        lines.extend(
            [
                "TLSConnect=psk",
                "TLSAccept=psk",
                f"TLSPSKIdentity={config.psk_identity}",
                f"TLSPSKFile={config.psk_file}",
            ]
        )
    lines.append(MANAGED_END)
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
