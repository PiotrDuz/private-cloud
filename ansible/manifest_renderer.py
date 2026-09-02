import subprocess
import tempfile
from shutil import copytree
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


def render_kustomization(
    base: Path,
    kustomization: Mapping[str, Any],
    command: Sequence[str],
) -> str:
    with tempfile.TemporaryDirectory(prefix="private-cloud-kustomize-") as directory:
        overlay = Path(directory)
        copytree(base.resolve(), overlay / "base")
        document = dict(kustomization)
        document["resources"] = ["base"]
        (overlay / "kustomization.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False),
            encoding="utf-8",
        )
        try:
            result = subprocess.run(
                kustomize_build_command(command, overlay),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or "Kustomize returned a non-zero status"
            raise RuntimeError(detail) from error
    reject_secrets(result.stdout)
    return result.stdout


def load_values(path: Path | None, standard_input: str) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8") if path else standard_input
    values = yaml.safe_load(source)
    if not isinstance(values, dict):
        raise ValueError("Manifest values must be a YAML mapping")
    return values


def kustomize_build_command(command: Sequence[str], overlay: Path) -> list[str]:
    if len(command) >= 2 and Path(command[-2]).name == "kustomize" and command[-1] == "build":
        return [*command, str(overlay), "--load-restrictor", "LoadRestrictionsNone"]
    if command and Path(command[-1]).name == "kustomize":
        return [*command, str(overlay), "--load-restrictor", "LoadRestrictionsNone"]
    raise ValueError("Kustomize command must end with 'kustomize' or 'kustomize build'")


def reject_secrets(output: str) -> None:
    resources = [resource for resource in yaml.safe_load_all(output) if resource]
    if any(_contains_secret(resource) for resource in resources):
        raise ValueError("Public manifest rendering cannot emit Secret resources")


def image_transform(image: str) -> dict[str, str]:
    if "@" in image:
        name, digest = image.rsplit("@", 1)
        last_component = name.rsplit("/", 1)[-1]
        if ":" in last_component:
            name = name.rsplit(":", 1)[0]
        return {"newName": name, "digest": digest}
    last_component = image.rsplit("/", 1)[-1]
    if ":" in last_component:
        name, tag = image.rsplit(":", 1)
        return {"newName": name, "newTag": tag}
    return {"newName": image}


def json_patch(operations: list[dict[str, Any]]) -> str:
    return yaml.safe_dump(operations, sort_keys=False)


def _contains_secret(resource: Any) -> bool:
    if not isinstance(resource, dict):
        return False
    if resource.get("kind") == "Secret":
        return True
    return resource.get("kind") == "List" and any(_contains_secret(item) for item in resource.get("items", []))
