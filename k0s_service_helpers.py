from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping

from installer_helpers import CommandRunner, InstallerError


def validate_kustomize_base(base_directory: Path) -> None:
    if not base_directory.is_dir():
        raise InstallerError(f"Kustomize base directory does not exist: {base_directory}")
    kustomization_path = base_directory / "kustomization.yaml"
    if not kustomization_path.is_file():
        raise InstallerError(
            f"Kustomize base is missing kustomization.yaml: {base_directory}"
        )


@contextmanager
def runtime_kustomize_overlay(
    base_directory: Path,
    patches: Mapping[str, str],
) -> Iterator[Path]:
    validate_kustomize_base(base_directory)
    overlay_path = Path(
        tempfile.mkdtemp(
            prefix=".kustomize-runtime-",
            dir=base_directory.parent,
        )
    )
    overlay_path.chmod(0o700)
    try:
        patch_paths = write_runtime_patches(overlay_path, patches)
        write_runtime_kustomization(base_directory, overlay_path, patch_paths)
        yield overlay_path
    finally:
        shutil.rmtree(overlay_path, ignore_errors=True)


def render_kustomize_overlay(overlay_path: Path) -> None:
    run_kustomize_command(["k0s", "kubectl", "kustomize", str(overlay_path)])


def apply_kustomize_overlay(overlay_path: Path) -> None:
    run_kustomize_command(["k0s", "kubectl", "apply", "-k", str(overlay_path)])


def apply_string_secret(
    namespace: str,
    name: str,
    values: Mapping[str, str],
) -> None:
    validate_kubernetes_name(namespace, "namespace")
    validate_kubernetes_name(name, "secret name")
    if not values:
        raise InstallerError("Secret values cannot be empty")
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9._-]+", key):
            raise InstallerError(f"Invalid secret key: {key}")
        if not isinstance(value, str) or not value:
            raise InstallerError(f"Secret value for {key} must be a nonempty string")

    manifest = render_string_secret(namespace, name, values)
    try:
        result = subprocess.run(
            ["k0s", "kubectl", "apply", "-f", "-"],
            input=manifest,
            text=True,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise InstallerError("Unable to run k0s kubectl") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        message = f"k0s kubectl apply secret failed ({result.returncode})"
        if detail:
            message = f"{message}: {detail}"
        raise InstallerError(message)


def service_dataset_spec(
    root_dataset: str,
    root_mountpoint: Path,
    relative_path: str,
) -> DatasetSpec:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise InstallerError(f"Invalid service dataset path: {relative_path}")
    return DatasetSpec(
        name=f"{root_dataset}/{relative_path}",
        mountpoint=root_mountpoint / path,
    )


def ensure_service_dataset(
    runner: CommandRunner,
    dataset: DatasetSpec,
    properties: Mapping[str, str],
) -> None:
    result = runner.run(
        ["zfs", "list", "-H", "-o", "name", dataset.name],
        check=False,
    )
    if result.returncode == 0:
        actual_mountpoint = zfs_value(runner, dataset.name, "mountpoint")
        if actual_mountpoint != str(dataset.mountpoint):
            raise InstallerError(
                f"{dataset.name} has mountpoint {actual_mountpoint}; "
                f"expected {dataset.mountpoint}"
            )
    else:
        runner.run(
            [
                "zfs",
                "create",
                "-o",
                f"mountpoint={dataset.mountpoint}",
                dataset.name,
            ]
        )

    for property_name, value in properties.items():
        runner.run(["zfs", "set", f"{property_name}={value}", dataset.name])
    if zfs_value(runner, dataset.name, "mounted") != "yes":
        runner.run(["zfs", "mount", dataset.name])


def ready_k0s_node_name(runner: CommandRunner) -> str:
    result = runner.run(["k0s", "kubectl", "get", "nodes", "-o", "json"])
    try:
        nodes = json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError as error:
        raise InstallerError("k0s returned invalid node JSON") from error

    for node in nodes:
        conditions = node.get("status", {}).get("conditions", [])
        if any(
            condition.get("type") == "Ready" and condition.get("status") == "True"
            for condition in conditions
        ):
            return str(node["metadata"]["name"])
    raise InstallerError("No Ready k0s node is available for the local volume")


def zfs_value(runner: CommandRunner, dataset: str, property_name: str) -> str:
    result = runner.run(
        ["zfs", "get", "-H", "-o", "value", property_name, dataset]
    )
    return result.stdout.strip()


def write_runtime_patches(
    overlay_path: Path,
    patches: Mapping[str, str],
) -> list[Path]:
    if not patches:
        raise InstallerError("Kustomize overlay requires at least one patch")

    patch_paths: list[Path] = []
    for filename, content in patches.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.yaml", filename):
            raise InstallerError(f"Invalid Kustomize patch filename: {filename}")
        if filename == "kustomization.yaml":
            raise InstallerError("Kustomize patch filename is reserved: kustomization.yaml")
        if not isinstance(content, str) or not content.strip():
            raise InstallerError(f"Kustomize patch is empty: {filename}")
        patch_path = overlay_path / filename
        patch_path.write_text(content, encoding="utf-8")
        patch_path.chmod(0o600)
        patch_paths.append(patch_path)
    return patch_paths


def write_runtime_kustomization(
    base_directory: Path,
    overlay_path: Path,
    patch_paths: list[Path],
) -> None:
    base_path = os.path.relpath(base_directory, overlay_path)
    lines = [
        "apiVersion: kustomize.config.k8s.io/v1beta1",
        "kind: Kustomization",
        "resources:",
        f"  - {json.dumps(base_path)}",
        "patches:",
    ]
    for patch_path in patch_paths:
        lines.append(f"  - path: {json.dumps(patch_path.name)}")
    kustomization_path = overlay_path / "kustomization.yaml"
    kustomization_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    kustomization_path.chmod(0o600)


def render_string_secret(
    namespace: str,
    name: str,
    values: Mapping[str, str],
) -> str:
    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        f"  name: {json.dumps(name)}",
        f"  namespace: {json.dumps(namespace)}",
        "type: Opaque",
        "stringData:",
    ]
    for key, value in values.items():
        lines.append(f"  {key}: {json.dumps(value)}")
    return "\n".join(lines) + "\n"


def run_kustomize_command(args: list[str]) -> None:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise InstallerError("Unable to run k0s kubectl") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        message = f"k0s kubectl command failed ({result.returncode})"
        if detail:
            message = f"{message}: {detail}"
        raise InstallerError(message)


def validate_kubernetes_name(value: str, label: str) -> None:
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", value):
        raise InstallerError(f"Invalid Kubernetes {label}: {value}")


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    mountpoint: Path
