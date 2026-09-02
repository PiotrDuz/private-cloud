from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {"dataset_path", "node_name", "image", "memory", "node_port"}
    if set(values) != required:
        raise ValueError(f"OnlyOffice manifest values must contain: {', '.join(sorted(required))}")
    string_values = required - {"node_port"}
    if not all(isinstance(values[key], str) and values[key] for key in string_values):
        raise ValueError("OnlyOffice manifest string values must be non-empty")
    if not isinstance(values["node_port"], int) or isinstance(values["node_port"], bool):
        raise ValueError("OnlyOffice manifest node_port must be an integer")
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [{"name": "onlyoffice/documentserver", **image_transform(values["image"])}],
        "patches": [
            {
                "target": {"version": "v1", "kind": "PersistentVolume", "name": "onlyoffice-data"},
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
                "target": {"group": "apps", "version": "v1", "kind": "Deployment", "name": "onlyoffice"},
                "patch": json_patch(
                    [
                        {
                            "op": "replace",
                            "path": "/spec/template/spec/containers/0/resources/requests/memory",
                            "value": values["memory"],
                        },
                        {
                            "op": "replace",
                            "path": "/spec/template/spec/containers/0/resources/limits/memory",
                            "value": values["memory"],
                        },
                    ]
                ),
            },
            {
                "target": {"version": "v1", "kind": "Service", "name": "onlyoffice-public"},
                "patch": json_patch(
                    [{"op": "replace", "path": "/spec/ports/0/nodePort", "value": values["node_port"]}]
                ),
            },
        ],
    }
