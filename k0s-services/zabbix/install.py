#!/usr/bin/env python3
from __future__ import annotations

import json
import os
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
    SERVICE_VOLUME_CAPACITY,
    apply_kustomize_overlay,
    apply_string_secret,
    parse_storage_quantity,
    ready_k0s_node_name,
    render_kustomize_overlay,
    runtime_kustomize_overlay,
    validate_kustomize_base,
    zfs_value,
)
from postgres_database import ensure_zabbix_database
from zabbix_api import configure_monitored_host, validate_template

NAMESPACE = "private-cloud"
POSTGRES_SERVICE = "postgres"
POSTGRES_DEPLOYMENT = "postgres"
ZABBIX_DATABASE_SECRET = "zabbix-postgres-credentials"
ZABBIX_PV = "zabbix-server-data"
ZABBIX_PVC = "zabbix-server-data"
PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
BASE_DIRECTORY = Path(__file__).resolve().parent / "kustomize" / "base"
ZABBIX_TEMPLATE_DIRECTORY = PROJECT_DIRECTORY / "zabbix"
ZABBIX_TEMPLATES = (
    ZABBIX_TEMPLATE_DIRECTORY / "zabbix-zfs-template.yaml",
    ZABBIX_TEMPLATE_DIRECTORY / "zabbix-memory-ecc-template.yaml",
)


def main() -> int:
    try:
        config = load_config()
        clear_password_environment()
        result = run_installation(config, CommandRunner())
    except InstallerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        clear_password_environment()

    print(json.dumps(result, sort_keys=True))
    return 0


def clear_password_environment() -> None:
    os.environ.pop("ZABBIX_ADMIN_PASSWORD", None)
    os.environ.pop("ZABBIX_DB_PASSWORD", None)


def run_installation(
    config: InstallConfig,
    runner: CommandRunner,
) -> dict[str, Any]:
    preflight(config, runner)
    prepare_database(config)
    dataset, storage_bytes = prepare_storage(config, runner)
    node_name = ready_k0s_node_name(runner)
    verify_existing_pv(node_name, dataset.mountpoint, runner)
    verify_existing_pvc(runner)
    apply_resources(config, node_name, dataset.mountpoint)
    restart_zabbix_deployments(runner)
    validate_installation(node_name, runner)
    registration = configure_zabbix(config)
    return installation_result(
        config,
        dataset,
        node_name,
        storage_bytes,
        registration,
    )


def preflight(config: InstallConfig, runner: CommandRunner) -> None:
    require_root()
    require_commands(["k0s", "mountpoint", "zfs"])
    validate_kustomize_base(BASE_DIRECTORY)
    for template_path in ZABBIX_TEMPLATES:
        if not template_path.is_file():
            raise InstallerError(f"Zabbix template not found: {template_path}")
        validate_template(template_path)
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
            "deployment",
            POSTGRES_DEPLOYMENT,
            "-n",
            NAMESPACE,
        ]
    )
    runner.run(
        [
            "k0s",
            "kubectl",
            "rollout",
            "status",
            f"deployment/{POSTGRES_DEPLOYMENT}",
            "-n",
            NAMESPACE,
            "--timeout=5m",
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


def prepare_database(config: InstallConfig) -> None:
    ensure_zabbix_database(
        NAMESPACE,
        config.database,
        config.database_username,
        config.database_password,
    )
    apply_string_secret(
        NAMESPACE,
        ZABBIX_DATABASE_SECRET,
        {
            "POSTGRES_DB": config.database,
            "POSTGRES_USER": config.database_username,
            "POSTGRES_PASSWORD": config.database_password,
        },
    )


def prepare_storage(
    config: InstallConfig,
    runner: CommandRunner,
) -> tuple[DatasetSpec, int]:
    root_mountpoint = zfs_value(runner, config.root_dataset, "mountpoint")
    if not root_mountpoint.startswith("/") or any(
        character.isspace() for character in root_mountpoint
    ):
        raise InstallerError(
            f"{config.root_dataset} needs an absolute mountpoint without whitespace"
        )
    dataset = dataset_spec(config, Path(root_mountpoint))
    storage_bytes = resolve_storage_bytes(config, dataset, runner)
    ensure_zabbix_dataset(dataset, runner, str(storage_bytes))
    runner.run(["mountpoint", "-q", str(dataset.mountpoint)])
    return dataset, storage_bytes


def resolve_storage_bytes(
    config: InstallConfig,
    dataset: DatasetSpec,
    runner: CommandRunner,
) -> int:
    requested_bytes = parse_storage_quantity(config.storage_size)
    existing_quantities = []
    for property_name in ("quota", "used"):
        result = runner.run(
            ["zfs", "get", "-Hp", "-o", "value", property_name, dataset.name],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip().isdecimal():
            existing_quantities.append(result.stdout.strip())
    if not existing_quantities:
        return requested_bytes

    required_bytes = max(
        parse_storage_quantity(value) for value in existing_quantities
    )
    if requested_bytes < required_bytes:
        minimum_size = minimum_configured_size(required_bytes)
        raise InstallerError(
            f"ZABBIX_STORAGE_SIZE={config.storage_size} cannot shrink existing "
            f"Zabbix storage; use at least {minimum_size}"
        )
    return requested_bytes


def minimum_configured_size(required_bytes: int) -> str:
    units = (
        ("E", 1000**6),
        ("P", 1000**5),
        ("T", 1000**4),
        ("G", 1000**3),
        ("M", 1000**2),
        ("K", 1000),
    )
    for suffix, multiplier in units:
        if required_bytes >= multiplier:
            amount = (required_bytes + multiplier - 1) // multiplier
            return f"{amount}{suffix}"
    return "1K"


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
        capacity = spec["capacity"]["storage"]
        values = spec["nodeAffinity"]["required"]["nodeSelectorTerms"][0][
            "matchExpressions"
        ][0]["values"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise InstallerError(
            f"Existing PersistentVolume {ZABBIX_PV} is malformed"
        ) from error
    if (
        path != str(mountpoint)
        or values != [node_name]
        or parse_storage_quantity(str(capacity))
        != parse_storage_quantity(SERVICE_VOLUME_CAPACITY)
    ):
        raise InstallerError(
            f"Existing PersistentVolume {ZABBIX_PV} uses a different path, node, "
            "or capacity"
        )


def verify_existing_pvc(runner: CommandRunner) -> None:
    result = runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "persistentvolumeclaim",
            ZABBIX_PVC,
            "-n",
            NAMESPACE,
            "-o",
            "json",
        ],
        check=False,
    )
    if result.returncode != 0:
        return
    try:
        claim = json.loads(result.stdout)
        requested = claim["spec"]["resources"]["requests"]["storage"]
        capacity = claim.get("status", {}).get("capacity", {}).get("storage")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise InstallerError(
            f"Existing PersistentVolumeClaim {ZABBIX_PVC} is malformed"
        ) from error
    expected = parse_storage_quantity(SERVICE_VOLUME_CAPACITY)
    values = [requested] if capacity is None else [requested, capacity]
    if any(parse_storage_quantity(str(value)) != expected for value in values):
        raise InstallerError(f"Existing {ZABBIX_PVC} does not use fixed 10Ti capacity")


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


def restart_zabbix_deployments(runner: CommandRunner) -> None:
    runner.run(
        [
            "k0s",
            "kubectl",
            "rollout",
            "restart",
            "deployment/zabbix-server",
            "deployment/zabbix-web",
            "-n",
            NAMESPACE,
        ]
    )


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
            "secret",
            ZABBIX_DATABASE_SECRET,
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


def configure_zabbix(config: InstallConfig) -> dict[str, Any]:
    api_url = f"http://127.0.0.1:{config.web_node_port}/api_jsonrpc.php"
    return configure_monitored_host(
        api_url,
        config.admin_username,
        config.admin_password,
        config.hostname,
        ZABBIX_TEMPLATES,
    )


def installation_result(
    config: InstallConfig,
    dataset: DatasetSpec,
    node_name: str,
    storage_bytes: int,
    registration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "database": config.database,
        "database_user": config.database_username,
        "dataset": dataset.name,
        "mountpoint": str(dataset.mountpoint),
        "node": node_name,
        "registered_host": registration["host"],
        "server_node_port": config.server_node_port,
        "storage_bytes": storage_bytes,
        "status": "installed",
        "templates": registration["templates"],
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
    storage: {value(SERVICE_VOLUME_CAPACITY)}
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
      storage: {value(SERVICE_VOLUME_CAPACITY)}
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
