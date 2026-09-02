#!/usr/bin/env python3
import argparse
import importlib
import json
import sys
from pathlib import Path

from manifest_renderer import load_values, render_kustomization


def render_manifests() -> None:
    try:
        arguments = parse_arguments()
        standard_input = sys.stdin.read() if arguments.values is None else ""
        values = load_values(arguments.values, standard_input)
        service = importlib.import_module(f"manifest_services.{arguments.service}")
        kustomization = service.build_kustomization(values, arguments.base)
        output = render_kustomization(arguments.base, kustomization, arguments.kustomize_command)
        sys.stdout.write(output)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        raise SystemExit(f"Manifest rendering failed: {error}") from error


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("service")
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--values", type=Path)
    parser.add_argument("--kustomize-command", default='["kustomize", "build"]')
    arguments = parser.parse_args()
    arguments.kustomize_command = _command_from_json(parser, arguments.kustomize_command)
    if arguments.values is None and sys.stdin.isatty():
        parser.error("provide --values or YAML on standard input")
    return arguments


def _command_from_json(parser: argparse.ArgumentParser, value: str) -> list[str]:
    try:
        command = json.loads(value)
    except json.JSONDecodeError as error:
        parser.error(f"--kustomize-command must be valid JSON: {error.msg}")
    if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
        parser.error("--kustomize-command must be a JSON array of command arguments")
    return command


if __name__ == "__main__":
    render_manifests()
