#!/usr/bin/env python3
from __future__ import annotations

import base64
import hmac
import json
import os
import sys
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from k0s_service_helpers import (
    SERVICE_VOLUME_CAPACITY,
    apply_kustomize_overlay,
    apply_string_secret,
    ensure_service_dataset,
    parse_storage_quantity,
    ready_k0s_node_name,
    render_kustomize_overlay,
    runtime_kustomize_overlay,
    validate_kustomize_base,
    zfs_value,
)

from install_helpers import (
    ADMIN_DATABASE,
    ADMIN_USERNAME,
    NAMESPACE,
    SECRET_NAME,
    SERVICE_NAME,
    CommandRunner,
    DatasetSpec,
    InstallerError,
    require_commands,
    require_root,
    PostgresConfig,
    dataset_spec,
    load_config,
)

BASE_DIRECTORY = Path(__file__).resolve().parent / "kustomize" / "base"


def main() -> int:
    try:
        config = load_config()
        os.environ.pop("POSTGRES_ADMIN_PASSWORD", None)
        result = run_installation(config, CommandRunner())
    except InstallerError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        os.environ.pop("POSTGRES_ADMIN_PASSWORD", None)

    print(json.dumps(result, sort_keys=True))
    return 0


def run_installation(
    config: PostgresConfig,
    runner: CommandRunner,
) -> dict[str, str]:
    root_mountpoint = preflight(config, runner)
    dataset = dataset_spec(config, root_mountpoint)
    ensure_service_dataset(
        runner,
        dataset,
        postgres_dataset_properties(config),
    )
    node_name = ready_k0s_node_name(runner)
    validate_existing_resources(config, dataset, node_name, runner)
    apply_resources(config, dataset, node_name, runner)
    wait_for_postgres(config, runner)
    validate_installation(config, dataset, runner)
    validate_postgres_settings(config, runner)
    return {
        "dataset": dataset.name,
        "namespace": NAMESPACE,
        "service": SERVICE_NAME,
        "shared_buffers": config.shared_buffers,
        "status": "installed",
    }


def preflight(config: PostgresConfig, runner: CommandRunner) -> Path:
    require_root()
    require_commands(["k0s", "mountpoint", "zfs"])
    validate_kustomize_base(BASE_DIRECTORY)

    root_result = runner.run(
        ["zfs", "list", "-H", "-o", "name", config.root_dataset],
        check=False,
    )
    if root_result.returncode != 0:
        raise InstallerError(f"ZFS dataset does not exist: {config.root_dataset}")
    if zfs_value(runner, config.root_dataset, "keystatus") == "unavailable":
        raise InstallerError(f"ZFS key is unavailable: {config.root_dataset}")
    if zfs_value(runner, config.root_dataset, "mounted") != "yes":
        raise InstallerError(f"ZFS dataset is not mounted: {config.root_dataset}")

    root_mountpoint = Path(zfs_value(runner, config.root_dataset, "mountpoint"))
    if not root_mountpoint.is_absolute() or any(
        character.isspace() for character in str(root_mountpoint)
    ):
        raise InstallerError(
            f"{config.root_dataset} needs an absolute mountpoint without whitespace"
        )
    runner.run(["mountpoint", "-q", str(root_mountpoint)])
    runner.run(["k0s", "kubectl", "get", "nodes"])
    return root_mountpoint


def postgres_dataset_properties(config: PostgresConfig) -> dict[str, str]:
    return {
        "recordsize": "8K",
        "compression": "zstd",
        "prefetch": "none",
        "primarycache": "all",
        "logbias": "latency",
        "quota": config.volume_size,
        "reservation": config.volume_size,
    }


def validate_existing_resources(
    config: PostgresConfig,
    dataset: DatasetSpec,
    node_name: str,
    runner: CommandRunner,
) -> None:
    validate_existing_secret(config, runner)
    validate_existing_pv(dataset, node_name, runner)
    validate_existing_pvc(runner)


def validate_existing_secret(
    config: PostgresConfig,
    runner: CommandRunner,
) -> None:
    result = runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "get",
            "secret",
            SECRET_NAME,
            "-o",
            "json",
        ],
        check=False,
    )
    if result.returncode != 0:
        return
    try:
        data = json.loads(result.stdout).get("data", {})
        existing = {
            key: base64.b64decode(data[key], validate=True).decode("utf-8")
            for key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        }
    except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstallerError("Existing PostgreSQL credentials secret is invalid") from error
    expected = {
        "POSTGRES_DB": ADMIN_DATABASE,
        "POSTGRES_USER": ADMIN_USERNAME,
        "POSTGRES_PASSWORD": config.admin_password,
    }
    for key, value in expected.items():
        if not hmac.compare_digest(existing[key], value):
            raise InstallerError(
                f"Existing {SECRET_NAME} differs for {key}; refusing to desynchronize PostgreSQL"
            )


def validate_existing_pv(
    dataset: DatasetSpec,
    node_name: str,
    runner: CommandRunner,
) -> None:
    result = runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "persistentvolume",
            "postgres-local-pv",
            "-o",
            "json",
        ],
        check=False,
    )
    if result.returncode != 0:
        return
    try:
        spec = json.loads(result.stdout)["spec"]
        actual_path = spec["local"]["path"]
        capacity = spec["capacity"]["storage"]
        terms = spec["nodeAffinity"]["required"]["nodeSelectorTerms"]
        expression = terms[0]["matchExpressions"][0]
        values = expression["values"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise InstallerError("Existing PostgreSQL persistent volume is invalid") from error
    if (
        actual_path != str(dataset.mountpoint)
        or node_name not in values
        or parse_storage_quantity(str(capacity))
        != parse_storage_quantity(SERVICE_VOLUME_CAPACITY)
    ):
        raise InstallerError(
            "Existing PostgreSQL persistent volume uses a different path, node, "
            "or capacity"
        )


def validate_existing_pvc(runner: CommandRunner) -> None:
    result = runner.run(
        [
            "k0s",
            "kubectl",
            "get",
            "persistentvolumeclaim",
            "postgres-data",
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
            "Existing PostgreSQL persistent volume claim is invalid"
        ) from error
    expected = parse_storage_quantity(SERVICE_VOLUME_CAPACITY)
    values = [requested] if capacity is None else [requested, capacity]
    if any(parse_storage_quantity(str(value)) != expected for value in values):
        raise InstallerError("Existing PostgreSQL volume does not use fixed 10Ti capacity")


def apply_resources(
    config: PostgresConfig,
    dataset: DatasetSpec,
    node_name: str,
    runner: CommandRunner,
) -> None:
    with runtime_kustomize_overlay(
        BASE_DIRECTORY,
        render_runtime_patches(config, dataset, node_name),
    ) as overlay_path:
        render_kustomize_overlay(overlay_path)
        runner.run(
            [
                "k0s",
                "kubectl",
                "apply",
                "-f",
                str(BASE_DIRECTORY / "namespace.yaml"),
            ]
        )
        apply_string_secret(
            NAMESPACE,
            SECRET_NAME,
            {
                "POSTGRES_DB": ADMIN_DATABASE,
                "POSTGRES_USER": ADMIN_USERNAME,
                "POSTGRES_PASSWORD": config.admin_password,
            },
        )
        apply_kustomize_overlay(overlay_path)


def wait_for_postgres(config: PostgresConfig, runner: CommandRunner) -> None:
    runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "rollout",
            "status",
            "deployment/postgres",
            "--timeout=300s",
        ]
    )
    runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "wait",
            "--for=condition=Ready",
            "pod",
            "-l",
            "app.kubernetes.io/name=postgres",
            "--timeout=300s",
        ]
    )
    runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "exec",
            "deployment/postgres",
            "--",
            "pg_isready",
            "-U",
            ADMIN_USERNAME,
            "-d",
            ADMIN_DATABASE,
        ]
    )


def validate_installation(
    config: PostgresConfig,
    dataset: DatasetSpec,
    runner: CommandRunner,
) -> None:
    for property_name, value in postgres_dataset_properties(config).items():
        actual = zfs_value(runner, dataset.name, property_name)
        if actual != value:
            raise InstallerError(
                f"{dataset.name} has {property_name}={actual}; expected {value}"
            )
    runner.run(["mountpoint", "-q", str(dataset.mountpoint)])
    for resource in (
        "persistentvolume/postgres-local-pv",
        "persistentvolumeclaim/postgres-data",
        f"service/{SERVICE_NAME}",
        "deployment/postgres",
        f"secret/{SECRET_NAME}",
    ):
        arguments = ["k0s", "kubectl"]
        if resource.startswith(
            ("persistentvolumeclaim", "service", "deployment", "secret")
        ):
            arguments.extend(["-n", NAMESPACE])
        arguments.extend(["get", resource])
        runner.run(arguments)


def validate_postgres_settings(
    config: PostgresConfig,
    runner: CommandRunner,
) -> None:
    shared_buffers = runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "exec",
            "deployment/postgres",
            "--",
            "psql",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            ADMIN_USERNAME,
            "-d",
            ADMIN_DATABASE,
            "-c",
            "SELECT pg_size_bytes(current_setting('shared_buffers'));",
        ]
    ).stdout.strip()
    if shared_buffers != str(config.shared_buffers_bytes):
        raise InstallerError(
            "PostgreSQL shared_buffers is "
            f"{shared_buffers}; expected {config.shared_buffers_bytes} bytes"
        )
    settings = runner.run(
        [
            "k0s",
            "kubectl",
            "-n",
            NAMESPACE,
            "exec",
            "deployment/postgres",
            "--",
            "psql",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            ADMIN_USERNAME,
            "-d",
            ADMIN_DATABASE,
            "-c",
            "SHOW full_page_writes; SHOW wal_compression; SHOW wal_init_zero; "
            "SHOW wal_recycle; SHOW data_checksums;",
        ]
    ).stdout.splitlines()
    if settings != ["off", "off", "off", "off", "off"]:
        raise InstallerError(
            "PostgreSQL WAL, full-page-write, or checksum settings are not disabled"
        )


def render_runtime_patches(
    config: PostgresConfig,
    dataset: DatasetSpec,
    node_name: str,
) -> dict[str, str]:
    value = json.dumps
    return {
        "persistent-volume.yaml": f"""apiVersion: v1
kind: PersistentVolume
metadata:
  name: postgres-local-pv
spec:
  capacity:
    storage: {value(SERVICE_VOLUME_CAPACITY)}
  local:
    path: {value(str(dataset.mountpoint))}
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
  name: postgres-data
  namespace: {NAMESPACE}
spec:
  resources:
    requests:
      storage: {value(SERVICE_VOLUME_CAPACITY)}
""",
        "deployment.yaml": f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  namespace: {NAMESPACE}
spec:
  template:
    spec:
      containers:
        - name: postgres
          args:
            - -c
            - shared_buffers={config.shared_buffers}
            - -c
            - full_page_writes=off
            - -c
            - wal_compression=off
            - -c
            - wal_init_zero=off
            - -c
            - wal_recycle=off
          resources:
            requests:
              memory: {value(config.max_ram)}
            limits:
              memory: {value(config.max_ram)}
          readinessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - {value(ADMIN_USERNAME)}
                - -d
                - {value(ADMIN_DATABASE)}
          livenessProbe:
            exec:
              command:
                - pg_isready
                - -U
                - {value(ADMIN_USERNAME)}
                - -d
                - {value(ADMIN_DATABASE)}
""",
    }


if __name__ == "__main__":
    raise SystemExit(main())
