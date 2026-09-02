from pathlib import Path
from typing import Any, Mapping

import yaml

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {
        "dataset_path",
        "node_name",
        "image",
        "memory",
        "hostname",
        "default_email",
        "database_name",
        "database_username",
        "postgres_service",
        "node_port",
    }
    if set(values) != required:
        raise ValueError(f"Grist manifest values must contain: {', '.join(sorted(required))}")
    string_values = required - {"node_port"}
    if not all(isinstance(values[key], str) and values[key] for key in string_values):
        raise ValueError("Grist manifest string values must be non-empty")
    if not isinstance(values["node_port"], int) or isinstance(values["node_port"], bool):
        raise ValueError("Grist manifest node_port must be an integer")
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [{"name": "gristlabs/grist", **image_transform(values["image"])}],
        "patches": [
            {
                "target": {"version": "v1", "kind": "PersistentVolume", "name": "grist-data"},
                "patch": json_patch(
                    [
                        {"op": "replace", "path": "/spec/local/path", "value": values["dataset_path"]},
                        {
                            "op": "replace",
                            "path": "/spec/nodeAffinity/required/nodeSelectorTerms/0/matchExpressions/0/values",
                            "value": [values["node_name"]],
                        },
                    ]
                ),
            },
            {
                "target": {"group": "apps", "version": "v1", "kind": "Deployment", "name": "grist"},
                "patch": _deployment_patch(values),
            },
            {
                "target": {"version": "v1", "kind": "Service", "name": "grist-public"},
                "patch": json_patch(
                    [{"op": "replace", "path": "/spec/ports/0/nodePort", "value": values["node_port"]}]
                ),
            },
        ],
    }

def _deployment_patch(values: Mapping[str, Any]) -> str:
    home_url = f"https://{values['hostname']}"
    return yaml.safe_dump(
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "grist"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "grist",
                                "env": [
                                    {"name": "APP_HOME_URL", "value": home_url},
                                    {"name": "APP_DOC_URL", "value": home_url},
                                    {"name": "GRIST_DEFAULT_EMAIL", "value": values["default_email"]},
                                    {"name": "TYPEORM_HOST", "value": values["postgres_service"]},
                                    {"name": "TYPEORM_DATABASE", "value": values["database_name"]},
                                    {"name": "TYPEORM_USERNAME", "value": values["database_username"]},
                                ],
                                "resources": {
                                    "requests": {"memory": values["memory"]},
                                    "limits": {"memory": values["memory"]},
                                },
                            }
                        ]
                    }
                }
            },
        },
        sort_keys=False,
    )
