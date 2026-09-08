#!/usr/bin/env python3
"""Expand storage monitoring from the shared dataset catalog."""
import json
import sys
from pathlib import Path
import yaml
from storage_template_helpers import expand_datasets


def main():
    configuration = json.load(sys.stdin)
    template = yaml.safe_load(Path(configuration["template_path"]).read_text())
    expand_datasets(template, configuration["datasets"])
    print(json.dumps(template))


if __name__ == "__main__":
    main()
