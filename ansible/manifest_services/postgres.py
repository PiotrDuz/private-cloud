from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {"dataset_path", "node_name", "image", "memory", "shared_buffers"}
    if set(values) != required or not all(isinstance(values[key], str) and values[key] for key in required):
        raise ValueError(f"PostgreSQL manifest values must contain: {', '.join(sorted(required))}")
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [{"name": "pgvector/pgvector", **image_transform(values["image"])}],
        "patches": [
            {
                "target": {"version": "v1", "kind": "PersistentVolume", "name": "postgres-local-pv"},
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
                "target": {"group": "apps", "version": "v1", "kind": "Deployment", "name": "postgres"},
                "patch": json_patch(
                    [
                        {
                            "op": "replace",
                            "path": "/spec/template/spec/containers/0/args/1",
                            "value": f"shared_buffers={values['shared_buffers']}",
                        },
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
