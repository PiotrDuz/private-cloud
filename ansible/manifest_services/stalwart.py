import json
from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {
        "dataset_path",
        "node_name",
        "image",
        "cli_image",
        "memory",
        "hostname",
        "database_name",
        "database_username",
        "https_node_port",
        "smtp_node_port",
        "submissions_node_port",
        "submission_node_port",
        "imaps_node_port",
    }
    _validate(values, required)
    config = json.loads(_base_file(base, "configmap.yaml")["data"]["config.json"])
    config["database"] = values["database_name"]
    config["authUsername"] = values["database_username"]
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [
            {"name": "stalwartlabs/stalwart", **image_transform(values["image"])},
            {
                "name": "ghcr.io/stalwartlabs/cli",
                **image_transform(values["cli_image"]),
            },
        ],
        "patches": [
            _patch(
                "v1",
                "PersistentVolume",
                "stalwart-data",
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
            _patch(
                "v1",
                "ConfigMap",
                "stalwart-config",
                [
                    {
                        "op": "replace",
                        "path": "/data/config.json",
                        "value": json.dumps(config, indent=2) + "\n",
                    },
                ],
            ),
            _merge_patch(
                "apps/v1",
                "StatefulSet",
                "stalwart",
                {
                    "spec": {
                        "template": {
                            "spec": {
                                "containers": [
                                    {
                                        "name": "stalwart",
                                        "env": [
                                            {
                                                "name": "STALWART_PUBLIC_URL",
                                                "value": f"https://{values['hostname']}",
                                            }
                                        ],
                                        "resources": {
                                            "requests": {"memory": values["memory"]},
                                            "limits": {"memory": values["memory"]},
                                        },
                                    }
                                ]
                            },
                        }
                    },
                },
            ),
            _merge_patch(
                "v1",
                "Service",
                "stalwart-public",
                {
                    "spec": {
                        "ports": [
                            {"name": name, "nodePort": values[key]}
                            for name, key in (
                                ("https", "https_node_port"),
                                ("smtp", "smtp_node_port"),
                                ("submissions", "submissions_node_port"),
                                ("submission", "submission_node_port"),
                                ("imaps", "imaps_node_port"),
                            )
                        ]
                    },
                },
            ),
        ],
    }


def _validate(values: Mapping[str, Any], required: set[str]) -> None:
    if set(values) != required:
        raise ValueError(
            f"Stalwart manifest values must contain: {', '.join(sorted(required))}"
        )
    ports = {key for key in required if key.endswith("_node_port")}
    if not all(
        isinstance(values[key], int) and not isinstance(values[key], bool)
        for key in ports
    ):
        raise ValueError("Stalwart manifest NodePorts must be integers")
    if not all(
        isinstance(values[key], str) and values[key] for key in required - ports
    ):
        raise ValueError("Stalwart manifest string values must be non-empty")


def _base_file(base: Path, name: str) -> dict[str, Any]:
    import yaml

    return yaml.safe_load((base / name).read_text(encoding="utf-8"))


def _patch(
    api_version: str, kind: str, name: str, operations: list[dict[str, Any]]
) -> dict[str, Any]:
    target = {"version": api_version, "kind": kind, "name": name}
    if "/" in api_version:
        target["group"], target["version"] = api_version.split("/", 1)
    return {"target": target, "patch": json_patch(operations)}


def _merge_patch(
    api_version: str, kind: str, name: str, content: dict[str, Any]
) -> dict[str, Any]:
    import yaml

    content = {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {"name": name},
        **content,
    }
    return {
        "target": {"kind": kind, "name": name},
        "patch": yaml.safe_dump(content, sort_keys=False),
    }
