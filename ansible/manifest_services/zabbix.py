from pathlib import Path
from typing import Any, Mapping

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {
        "dataset_path",
        "node_name",
        "server_image",
        "web_image",
        "server_node_port",
        "web_node_port",
    }
    _validate(values, required)
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [
            {
                "name": "zabbix/zabbix-server-pgsql",
                **image_transform(values["server_image"]),
            },
            {
                "name": "zabbix/zabbix-web-nginx-pgsql",
                **image_transform(values["web_image"]),
            },
        ],
        "patches": [
            _patch(
                "v1",
                "PersistentVolume",
                "zabbix-server-data",
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
                "Service",
                "zabbix-server",
                [
                    {
                        "op": "replace",
                        "path": "/spec/ports/0/nodePort",
                        "value": values["server_node_port"],
                    }
                ],
            ),
            _patch(
                "v1",
                "Service",
                "zabbix-web",
                [
                    {
                        "op": "replace",
                        "path": "/spec/ports/0/nodePort",
                        "value": values["web_node_port"],
                    }
                ],
            ),
        ],
    }


def _validate(values: Mapping[str, Any], required: set[str]) -> None:
    if set(values) != required:
        raise ValueError(
            f"Zabbix manifest values must contain: {', '.join(sorted(required))}"
        )
    ports = {"server_node_port", "web_node_port"}
    if not all(
        isinstance(values[key], int) and not isinstance(values[key], bool)
        for key in ports
    ):
        raise ValueError("Zabbix manifest NodePorts must be integers")
    if not all(
        isinstance(values[key], str) and values[key] for key in required - ports
    ):
        raise ValueError("Zabbix manifest string values must be non-empty")


def _patch(
    api_version: str, kind: str, name: str, operations: list[dict[str, Any]]
) -> dict[str, Any]:
    target = {"version": api_version, "kind": kind, "name": name}
    if "/" in api_version:
        target["group"], target["version"] = api_version.split("/", 1)
    return {"target": target, "patch": json_patch(operations)}
