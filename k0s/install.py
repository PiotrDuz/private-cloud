#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from install_helpers import (
    CommandRunner,
    DatasetSpec,
    InstallConfig,
    InstallerError,
    command_exists,
    ensure_dataset,
    load_config,
    require_commands,
    require_root,
    write_managed_file,
    zfs_size_bytes,
    zfs_value,
)

ZFS_MOUNT_SERVICE = "zfs-unlock-mount.service"
CONTROLLER_DROP_IN = Path(
    "/etc/systemd/system/k0scontroller.service.d/zfs.conf"
)


def main() -> int:
    try:
        result = run_installation(load_config(), CommandRunner())
    except InstallerError as error:
        print(f"ERROR: {error}", file=os.sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


def run_installation(
    config: InstallConfig,
    runner: CommandRunner,
) -> dict[str, Any]:
    preflight(config, runner)
    datasets = build_dataset_layout(config, runner)
    prepare_datasets(config, datasets, runner)
    configure_boot_dependency(datasets, runner)
    install_k0s_binary(config, runner)
    install_controller(datasets, runner)
    node_name = wait_for_ready_node(runner)
    validate_installation(datasets, runner)
    return installation_result(config, datasets, node_name)


def preflight(config: InstallConfig, runner: CommandRunner) -> None:
    require_root()
    require_commands(
        ["curl", "mountpoint", "sh", "systemctl", "zfs", "zpool"]
    )
    root_result = runner.run(
        ["zfs", "list", "-H", "-o", "name", config.root_dataset],
        check=False,
    )
    if root_result.returncode != 0:
        raise InstallerError(f"ZFS dataset does not exist: {config.root_dataset}")
    runner.run(["zpool", "list", config.root_dataset.split("/", 1)[0]])

    mount_service = runner.run(
        ["systemctl", "cat", ZFS_MOUNT_SERVICE],
        check=False,
    )
    if mount_service.returncode != 0:
        raise InstallerError(
            f"Install the ZFS boot service before k0s: {ZFS_MOUNT_SERVICE}"
        )


def build_dataset_layout(
    config: InstallConfig,
    runner: CommandRunner,
) -> dict[str, DatasetSpec]:
    root_mountpoint = zfs_value(
        runner,
        config.root_dataset,
        "mountpoint",
    )
    if not root_mountpoint.startswith("/") or any(
        character.isspace() for character in root_mountpoint
    ):
        raise InstallerError(
            f"{config.root_dataset} needs an absolute mountpoint without whitespace"
        )

    root_path = Path(root_mountpoint)
    runtime_path = root_path / "k0s"
    backup_path = root_path / "backup"
    no_backup_path = root_path / "no-backup"
    return {
        "backup": DatasetSpec(f"{config.root_dataset}/backup", backup_path),
        "backup_k0s": DatasetSpec(
            f"{config.root_dataset}/backup/k0s",
            backup_path / "k0s",
        ),
        "config": DatasetSpec(
            f"{config.root_dataset}/backup/k0s/config",
            runtime_path,
        ),
        "services": DatasetSpec(
            f"{config.root_dataset}/backup/k0s/services",
            backup_path / "k0s" / "services",
        ),
        "no_backup": DatasetSpec(
            f"{config.root_dataset}/no-backup",
            no_backup_path,
        ),
        "no_backup_k0s": DatasetSpec(
            f"{config.root_dataset}/no-backup/k0s",
            no_backup_path / "k0s",
        ),
        "no_backup_services": DatasetSpec(
            f"{config.root_dataset}/no-backup/k0s/services",
            no_backup_path / "k0s" / "services",
        ),
        "images": DatasetSpec(
            f"{config.root_dataset}/no-backup/k0s/images",
            runtime_path / "containerd",
        ),
        "ephemeral": DatasetSpec(
            f"{config.root_dataset}/no-backup/k0s/ephemeral",
            runtime_path / "kubelet",
        ),
    }


def prepare_datasets(
    config: InstallConfig,
    datasets: dict[str, DatasetSpec],
    runner: CommandRunner,
) -> None:
    if zfs_value(runner, config.root_dataset, "keystatus") == "unavailable":
        runner.run(["zfs", "load-key", config.root_dataset])
    if zfs_value(runner, config.root_dataset, "mounted") != "yes":
        runner.run(["zfs", "mount", config.root_dataset])

    for dataset in datasets.values():
        ensure_dataset(runner, dataset)

    quotas = {
        "config": config.config_quota,
        "images": config.images_quota,
        "ephemeral": config.ephemeral_quota,
    }
    for name, quota in quotas.items():
        apply_dataset_quota(datasets[name], quota, runner)


def apply_dataset_quota(
    dataset: DatasetSpec,
    quota: str,
    runner: CommandRunner,
) -> None:
    requested_bytes = zfs_size_bytes(quota)
    runner.run(["zfs", "set", f"quota={quota}", dataset.name])
    actual = runner.run(
        ["zfs", "get", "-Hp", "-o", "value", "quota", dataset.name]
    ).stdout.strip()
    if not actual.isdecimal() or int(actual) != requested_bytes:
        raise InstallerError(f"Failed to apply quota={quota} to {dataset.name}")


def configure_boot_dependency(
    datasets: dict[str, DatasetSpec],
    runner: CommandRunner,
) -> None:
    write_managed_file(
        CONTROLLER_DROP_IN,
        render_controller_drop_in(datasets),
        0o644,
    )
    runner.run(["systemctl", "daemon-reload"])


def install_k0s_binary(
    config: InstallConfig,
    runner: CommandRunner,
) -> None:
    if command_exists("k0s"):
        return

    installer_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="k0s-installer-", delete=False) as file:
            installer_path = Path(file.name)
        runner.run(
            [
                "curl",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--fail",
                "--silent",
                "--show-error",
                "https://get.k0s.sh",
                "-o",
                str(installer_path),
            ]
        )
        environment = os.environ.copy()
        environment["K0S_VERSION"] = config.k0s_version
        runner.run(["sh", str(installer_path)], env=environment)
    finally:
        if installer_path is not None:
            installer_path.unlink(missing_ok=True)

    require_commands(["k0s"])


def install_controller(
    datasets: dict[str, DatasetSpec],
    runner: CommandRunner,
) -> None:
    service_result = runner.run(
        [
            "systemctl",
            "list-unit-files",
            "k0scontroller.service",
            "--no-legend",
        ],
        check=False,
    )
    if service_result.stdout.strip():
        definition = runner.run(["systemctl", "cat", "k0scontroller.service"])
        expected_paths = (
            f"--config={datasets['config'].mountpoint / 'k0s.yaml'}",
            f"--data-dir={datasets['config'].mountpoint}",
            f"--kubelet-root-dir={datasets['ephemeral'].mountpoint}",
        )
        if not all(path in definition.stdout for path in expected_paths):
            raise InstallerError("Existing k0s service uses a different storage layout")
        runner.run(["systemctl", "is-active", "--quiet", "k0scontroller.service"])
        return

    cluster_config = datasets["config"].mountpoint / "k0s.yaml"
    generated_config = runner.run(["k0s", "config", "create"])
    write_managed_file(cluster_config, generated_config.stdout, 0o600)
    runner.run(
        [
            "k0s",
            "install",
            "controller",
            "--enable-worker",
            "--no-taints",
            f"--config={cluster_config}",
            f"--data-dir={datasets['config'].mountpoint}",
            f"--kubelet-root-dir={datasets['ephemeral'].mountpoint}",
        ]
    )
    runner.run(["systemctl", "daemon-reload"])
    runner.run(["k0s", "start"])


def wait_for_ready_node(runner: CommandRunner) -> str:
    for _ in range(60):
        result = runner.run(
            ["k0s", "kubectl", "get", "nodes", "-o", "json"],
            check=False,
        )
        if result.returncode == 0:
            try:
                nodes = json.loads(result.stdout).get("items", [])
            except json.JSONDecodeError:
                nodes = []
            for node in nodes:
                conditions = node.get("status", {}).get("conditions", [])
                if any(
                    condition.get("type") == "Ready"
                    and condition.get("status") == "True"
                    for condition in conditions
                ):
                    return str(node["metadata"]["name"])
        time.sleep(5)
    raise InstallerError("The k0s node did not become Ready within five minutes")


def validate_installation(
    datasets: dict[str, DatasetSpec],
    runner: CommandRunner,
) -> None:
    runner.run(["systemctl", "is-active", "--quiet", "k0scontroller.service"])
    for dataset in datasets.values():
        if zfs_value(runner, dataset.name, "mounted") != "yes":
            raise InstallerError(f"ZFS dataset is not mounted: {dataset.name}")
        runner.run(["mountpoint", "-q", str(dataset.mountpoint)])


def installation_result(
    config: InstallConfig,
    datasets: dict[str, DatasetSpec],
    node_name: str,
) -> dict[str, Any]:
    return {
        "datasets": [dataset.name for dataset in datasets.values()],
        "leaf_quotas": {
            datasets["config"].name: config.config_quota,
            datasets["images"].name: config.images_quota,
            datasets["ephemeral"].name: config.ephemeral_quota,
        },
        "k0s_version": config.k0s_version,
        "node": node_name,
        "status": "installed",
        "storage_model": "backup-split",
    }


def render_controller_drop_in(datasets: dict[str, DatasetSpec]) -> str:
    checks = "\n".join(
        f"ExecStartPre=/usr/bin/mountpoint -q {dataset.mountpoint}"
        for dataset in datasets.values()
    )
    return f"""[Unit]
Requires={ZFS_MOUNT_SERVICE}
After={ZFS_MOUNT_SERVICE}

[Service]
{checks}
"""


if __name__ == "__main__":
    raise SystemExit(main())
