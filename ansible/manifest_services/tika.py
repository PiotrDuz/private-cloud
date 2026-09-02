from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {"dataset_path", "node_name", "image", "memory"}
    if set(values) != required or not all(isinstance(values[key], str) and values[key] for key in required):
        raise ValueError(f"Apache Tika manifest values must contain: {', '.join(sorted(required))}")
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [{"name": "apache/tika", **image_transform(values["image"])}],
        "patches": [
            {
                "target": {"version": "v1", "kind": "PersistentVolume", "name": "tika-data"},
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
                "target": {"group": "apps", "version": "v1", "kind": "Deployment", "name": "tika"},
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
        ],
    }
