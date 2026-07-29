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
    configure_local_volumes(config, datasets, node_name, runner)
    validate_installation(config, datasets, runner)
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
        raise InstallerError(
            "k0scontroller.service already exists; refusing to replace the cluster"
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
    k0s_path = root_path / "k0s"
    k8s_path = root_path / "k8s"
    return {
        "k0s": DatasetSpec(f"{config.root_dataset}/k0s", k0s_path),
        "config": DatasetSpec(
            f"{config.root_dataset}/k0s/config",
            k0s_path / "config",
        ),
        "images": DatasetSpec(
            f"{config.root_dataset}/k0s/images",
            k0s_path / "images",
        ),
        "ephemeral": DatasetSpec(
            f"{config.root_dataset}/k0s/ephemeral",
            k0s_path / "containerd",
        ),
        "k8s": DatasetSpec(f"{config.root_dataset}/k8s", k8s_path),
        "volumes": DatasetSpec(
            f"{config.root_dataset}/k8s/volumes",
            k8s_path / "volumes",
        ),
        "services_backed": DatasetSpec(
            f"{config.root_dataset}/k0s/services-backed",
            k0s_path / "services-backed",
        ),
        "services_no_backup": DatasetSpec(
            f"{config.root_dataset}/k0s/services-no-backup",
            k0s_path / "services-no-backup",
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

    volumes = datasets["volumes"]
    for index in range(1, config.pv_count + 1):
        suffix = f"{index:02d}"
        pv_dataset = DatasetSpec(
            f"{volumes.name}/pv{suffix}",
            volumes.mountpoint / f"pv{suffix}",
        )
        ensure_dataset(runner, pv_dataset)
        runner.run(
            [
                "zfs",
                "set",
                f"quota={config.pv_size}",
                f"reservation={config.pv_size}",
                pv_dataset.name,
            ]
        )


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
            f"--data-dir={datasets['k0s'].mountpoint}",
            f"--kubelet-root-dir={datasets['ephemeral'].mountpoint / 'kubelet'}",
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


def configure_local_volumes(
    config: InstallConfig,
    datasets: dict[str, DatasetSpec],
    node_name: str,
    runner: CommandRunner,
) -> None:
    manifest = render_storage_manifest(
        config,
        datasets["volumes"].mountpoint,
        node_name,
    )
    storage_manifest = datasets["config"].mountpoint / "local-zfs-storage.yaml"
    write_managed_file(storage_manifest, manifest, 0o644)
    runner.run(["k0s", "kubectl", "apply", "-f", str(storage_manifest)])


def validate_installation(
    config: InstallConfig,
    datasets: dict[str, DatasetSpec],
    runner: CommandRunner,
) -> None:
    runner.run(["systemctl", "is-active", "--quiet", "k0scontroller.service"])
    for dataset in datasets.values():
        if zfs_value(runner, dataset.name, "mounted") != "yes":
            raise InstallerError(f"ZFS dataset is not mounted: {dataset.name}")
        runner.run(["mountpoint", "-q", str(dataset.mountpoint)])

    runner.run(["k0s", "kubectl", "get", "storageclass", "local-zfs"])
    for index in range(1, config.pv_count + 1):
        runner.run(
            [
                "k0s",
                "kubectl",
                "get",
                "persistentvolume",
                f"local-zfs-pv-{index:02d}",
            ]
        )


def installation_result(
    config: InstallConfig,
    datasets: dict[str, DatasetSpec],
    node_name: str,
) -> dict[str, Any]:
    volumes = datasets["volumes"]
    return {
        "datasets": [dataset.name for dataset in datasets.values()],
        "k0s_version": config.k0s_version,
        "node": node_name,
        "persistent_volumes": [
            f"{volumes.name}/pv{index:02d}"
            for index in range(1, config.pv_count + 1)
        ],
        "status": "installed",
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


def render_storage_manifest(
    config: InstallConfig,
    volumes_root: Path,
    node_name: str,
) -> str:
    documents = [
        """apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-zfs
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: kubernetes.io/no-provisioner
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
"""
    ]
    for index in range(1, config.pv_count + 1):
        suffix = f"{index:02d}"
        documents.append(
            f"""apiVersion: v1
kind: PersistentVolume
metadata:
  name: local-zfs-pv-{suffix}
  labels:
    storage.k0sproject.io/backend: zfs
spec:
  capacity:
    storage: {json.dumps(config.pv_size)}
  volumeMode: Filesystem
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: local-zfs
  local:
    path: {json.dumps(str(volumes_root / f"pv{suffix}"))}
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - {json.dumps(node_name)}
"""
        )
    return "---\n" + "---\n".join(documents)


if __name__ == "__main__":
    raise SystemExit(main())
