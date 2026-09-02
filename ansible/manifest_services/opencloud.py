import hashlib
from pathlib import Path
from typing import Any, Mapping

import yaml

from manifest_renderer import image_transform, json_patch


def build_kustomization(values: Mapping[str, Any], base: Path) -> dict[str, Any]:
    required = {
        "dataset_path",
        "node_name",
        "image",
        "drawio_image",
        "memory",
        "hostname",
        "onlyoffice_hostname",
        "node_port",
    }
    _validate(values, required)
    csp = _config(base, "csp-configmap.yaml").replace(
        "replace-with-onlyoffice-hostname", values["onlyoffice_hostname"]
    )
    annotations = {
        "private-cloud.example/apps-config-checksum": _digest(
            _config(base, "apps-configmap.yaml")
        ),
        "private-cloud.example/app-registry-config-checksum": _digest(
            _config(base, "app-registry-configmap.yaml")
        ),
        "private-cloud.example/csp-config-checksum": _digest(csp),
    }
    return {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "images": [
            {
                "name": "opencloudeu/opencloud-rolling",
                **image_transform(values["image"]),
            },
            {"name": "alpine", **image_transform(values["drawio_image"])},
        ],
        "patches": [
            _patch(
                "v1",
                "PersistentVolume",
                "opencloud-data",
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
                "opencloud-csp",
                [{"op": "replace", "path": "/data/csp.yaml", "value": csp}],
            ),
            _merge_patch(
                "apps/v1",
                "Deployment",
                "opencloud",
                {
                    "spec": {
                        "template": {
                            "metadata": {"annotations": annotations},
                            "spec": {
                                "containers": [
                                    {
                                        "name": "opencloud",
                                        "env": [
                                            {
                                                "name": "OC_URL",
                                                "value": f"https://{values['hostname']}",
                                            },
                                            {
                                                "name": "COLLABORATION_APP_ADDR",
                                                "value": f"https://{values['onlyoffice_hostname']}",
                                            },
                                            {
                                                "name": "COLLABORATION_APP_ICON",
                                                "value": f"https://{values['onlyoffice_hostname']}/web-apps/apps/documenteditor/main/resources/img/favicon.ico",
                                            },
                                            {
                                                "name": "COLLABORATION_WOPI_SRC",
                                                "value": f"https://{values['hostname']}",
                                            },
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
            _patch(
                "v1",
                "Service",
                "opencloud-public",
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


def _validate(values: Mapping[str, Any], required: set[str]) -> None:
    if set(values) != required:
        raise ValueError(
            f"OpenCloud manifest values must contain: {', '.join(sorted(required))}"
        )
    if not isinstance(values["node_port"], int) or isinstance(
        values["node_port"], bool
    ):
        raise ValueError("OpenCloud manifest node_port must be an integer")
    if not all(
        isinstance(values[key], str) and values[key] for key in required - {"node_port"}
    ):
        raise ValueError("OpenCloud manifest string values must be non-empty")


def _config(base: Path, name: str) -> str:
    document = yaml.safe_load((base / name).read_text(encoding="utf-8"))
    return next(iter(document["data"].values()))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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
