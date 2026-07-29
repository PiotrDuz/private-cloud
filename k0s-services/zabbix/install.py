#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from install_helpers import (
    CommandRunner,
    DatasetSpec,
    InstallConfig,
    InstallerError,
    dataset_spec,
    ensure_zabbix_dataset,
    load_config,
    require_commands,
    require_root,
)
from k0s_service_helpers import (
    apply_kustomize_overlay,
    ready_k0s_node_name,
    render_kustomize_overlay,
    runtime_kustomize_overlay,
    validate_kustomize_base,
    zfs_value,
)

NAMESPACE = "private-cloud"
POSTGRES_SECRET = "postgres-credentials"
POSTGRES_SERVICE = "postgres"
ZABBIX_PV = "zabbix-server-data"
ZABBIX_PVC = "zabbix-server-data"
BASE_DIRECTORY = Path(__file__).resolve().parent / "kustomize" / "base"


def main() -> int:
    try:
        result = run_installation(load_config(), CommandRunner())
    except InstallerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


def run_installation(
    config: InstallConfig,
    runner: CommandRunner,
) -> dict[str, Any]:
    preflight(config, runner)
    dataset = prepare_storage(config, runner)
    node_name = ready_k0s_node_name(runner)
    verify_existing_pv(node_name, dataset.mountpoint, runner)
    apply_resources(config, node_name, dataset.mountpoint)
    validate_installation(node_name, runner)
    return installation_result(config, dataset, node_name)


def preflight(config: InstallConfig, runner: CommandRunner) -> None:
    require_root()
    require_commands(["k0s", "mountpoint", "zfs"])
    validate_kustomize_base(BASE_DIRECTORY)
    root_result = runner.run(
        ["zfs", "list", "-H", "-o", "name", config.root_dataset],
        check=False,
    )
    if root_result.returncode != 0:
        raise InstallerError(f"ZFS dataset does not exist: {config.root_dataset}")
    runner.run(["k0s", "kubectl", "get", "namespace", NAMESPACE])
    runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "secret",
            POSTGRES_SECRET,
            "-n",
            NAMESPACE,
        ]
    )
    runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "service",
            POSTGRES_SERVICE,
            "-n",
            NAMESPACE,
        ]
    )


def prepare_storage(
    config: InstallConfig,
    runner: CommandRunner,
) -> DatasetSpec:
    root_mountpoint = zfs_value(runner, config.root_dataset, "mountpoint")
    if not root_mountpoint.startswith("/") or any(
        character.isspace() for character in root_mountpoint
    ):
        raise InstallerError(
            f"{config.root_dataset} needs an absolute mountpoint without whitespace"
        )
    dataset = dataset_spec(config, Path(root_mountpoint))
    ensure_zabbix_dataset(config, dataset, runner)
    runner.run(["mountpoint", "-q", str(dataset.mountpoint)])
    return dataset


def verify_existing_pv(
    node_name: str,
    mountpoint: Path,
    runner: CommandRunner,
) -> None:
    result = runner.run(
        ["k0s", "kubectl", "get", "persistentvolume", ZABBIX_PV, "-o", "json"],
        check=False,
    )
    if result.returncode != 0:
        return
    try:
        spec = json.loads(result.stdout)["spec"]
        path = spec["local"]["path"]
        values = spec["nodeAffinity"]["required"]["nodeSelectorTerms"][0][
            "matchExpressions"
        ][0]["values"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise InstallerError(f"Existing PersistentVolume {ZABBIX_PV} is malformed") from error
    if path != str(mountpoint) or values != [node_name]:
        raise InstallerError(
            f"Existing PersistentVolume {ZABBIX_PV} is pinned to different storage or node"
        )


def apply_resources(
    config: InstallConfig,
    node_name: str,
    mountpoint: Path,
) -> None:
    with runtime_kustomize_overlay(
        BASE_DIRECTORY,
        runtime_patches(config, node_name, mountpoint),
    ) as overlay_path:
        render_kustomize_overlay(overlay_path)
        apply_kustomize_overlay(overlay_path)


def validate_installation(node_name: str, runner: CommandRunner) -> None:
    runner.run(
        [
            "k0s",
            "kubectl",
            "wait",
            "--for=jsonpath={.status.phase}=Bound",
            f"persistentvolumeclaim/{ZABBIX_PVC}",
            "-n",
            NAMESPACE,
            "--timeout=5m",
        ]
    )
    for deployment in ("zabbix-server", "zabbix-web"):
        runner.run(
            [
                "k0s",
                "kubectl",
                "rollout",
                "status",
                f"deployment/{deployment}",
                "-n",
                NAMESPACE,
                "--timeout=10m",
            ]
        )
    for service in ("zabbix-server", "zabbix-web"):
        wait_for_endpoints(service, runner)
    runner.run(["k0s", "kubectl", "get", "persistentvolume", ZABBIX_PV])
    runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "service",
            "zabbix-server",
            "zabbix-web",
            "-n",
            NAMESPACE,
        ]
    )
    runner.run(["k0s", "kubectl", "get", "node", node_name])


def wait_for_endpoints(service: str, runner: CommandRunner) -> None:
    for _ in range(60):
        result = runner.run(
            [
                "k0s",
                "kubectl",
                "get",
                "endpoints",
                service,
                "-n",
                NAMESPACE,
                "-o",
                "json",
            ]
        )
        try:
            subsets = json.loads(result.stdout).get("subsets", [])
        except json.JSONDecodeError as error:
            raise InstallerError(f"Cannot parse endpoints for {service}") from error
        if any(subset.get("addresses") for subset in subsets):
            return
        time.sleep(5)
    raise InstallerError(f"Service {service} has no ready endpoints after five minutes")


def installation_result(
    config: InstallConfig,
    dataset: DatasetSpec,
    node_name: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset.name,
        "mountpoint": str(dataset.mountpoint),
        "node": node_name,
        "server_node_port": config.server_node_port,
        "status": "installed",
        "web_node_port": config.web_node_port,
    }


def runtime_patches(
    config: InstallConfig,
    node_name: str,
    mountpoint: Path,
) -> dict[str, str]:
    value = json.dumps
    return {
        "persistent-volume.yaml": f"""apiVersion: v1
kind: PersistentVolume
metadata:
  name: {ZABBIX_PV}
spec:
  capacity:
    storage: {value(config.storage_size)}
  local:
    path: {value(str(mountpoint))}
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - {value(node_name)}
""",
        "persistent-volume-claim.yaml": f"""apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {ZABBIX_PVC}
  namespace: {NAMESPACE}
spec:
  resources:
    requests:
      storage: {value(config.storage_size)}
""",
        "server-service.yaml": f"""apiVersion: v1
kind: Service
metadata:
  name: zabbix-server
  namespace: {NAMESPACE}
spec:
  ports:
    - name: zabbix-trapper
      port: 10051
      nodePort: {value(config.server_node_port)}
""",
        "web-service.yaml": f"""apiVersion: v1
kind: Service
metadata:
  name: zabbix-web
  namespace: {NAMESPACE}
spec:
  ports:
    - name: http
      port: 80
      nodePort: {value(config.web_node_port)}
""",
    }


if __name__ == "__main__":
    raise SystemExit(main())
