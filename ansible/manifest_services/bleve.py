from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {"dataset_path", "node_name"}
    if set(values) != required or not all(isinstance(values[key], str) and values[key] for key in required):
        raise ValueError(f"Bleve manifest values must contain: {', '.join(sorted(required))}")
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "patches": [
            {
                "target": {"version": "v1", "kind": "PersistentVolume", "name": "bleve-data"},
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
            }
        ],
    }
