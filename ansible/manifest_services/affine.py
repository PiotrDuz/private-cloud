import hashlib
from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {
        "dataset_path",
        "node_name",
        "image",
        "redis_image",
        "memory",
        "redis_memory",
        "node_port",
    }
    _validate(values, required)
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [
            {"name": "ghcr.io/toeverything/affine", **image_transform(values["image"])},
            {"name": "redis", **image_transform(values["redis_image"])},
        ],
        "patches": [
            _patch(
                "batch/v1",
                "Job",
                "affine-migration-0273",
                [
                    {
                        "op": "replace",
                        "path": "/metadata/name",
                        "value": _migration_job_name(values["image"]),
                    }
                ],
            ),
            _patch(
                "v1",
                "PersistentVolume",
                "affine-data",
                [
                    {
                        "op": "replace",
                        "path": "/spec/local/path",
                        "value": values["dataset_path"],
                    },
                    {
                        "op": "replace",
                        "path": "/spec/nodeAffinity/required/nodeSelectorTerms/0/matchExpressions/0/values",
                        "value": [values["node_name"]],
                    },
                ],
            ),
            _patch("apps/v1", "Deployment", "affine", _memory(values["memory"])),
            _patch(
                "apps/v1", "Deployment", "affine-redis", _memory(values["redis_memory"])
            ),
            _patch(
                "v1",
                "Service",
                "affine-public",
                [
                    {
                        "op": "replace",
                        "path": "/spec/ports/0/nodePort",
                        "value": values["node_port"],
                    }
                ],
            ),
        ],
    }


def _migration_job_name(image: str) -> str:
    revision = hashlib.sha256(image.encode("utf-8")).hexdigest()[:12]
    return f"affine-migration-{revision}"


def _memory(value: str) -> list[dict[str, Any]]:
    return [
        {
            "op": "replace",
            "path": "/spec/template/spec/containers/0/resources/requests/memory",
            "value": value,
        },
        {
            "op": "replace",
            "path": "/spec/template/spec/containers/0/resources/limits/memory",
            "value": value,
        },
    ]


def _validate(values: Mapping[str, Any], required: set[str]) -> None:
    if set(values) != required:
        raise ValueError(
            f"AFFiNE manifest values must contain: {', '.join(sorted(required))}"
        )
    if not isinstance(values["node_port"], int) or isinstance(
        values["node_port"], bool
    ):
        raise ValueError("AFFiNE manifest node_port must be an integer")
    if not all(
        isinstance(values[key], str) and values[key] for key in required - {"node_port"}
    ):
        raise ValueError("AFFiNE manifest string values must be non-empty")


def _patch(
    api_version: str, kind: str, name: str, operations: list[dict[str, Any]]
) -> dict[str, Any]:
    target = {"version": api_version, "kind": kind, "name": name}
    if "/" in api_version:
        target["group"], target["version"] = api_version.split("/", 1)
    return {"target": target, "patch": json_patch(operations)}
