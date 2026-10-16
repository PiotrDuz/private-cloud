#!/usr/bin/env python3
"""Create or refresh the scoped Meilisearch API key used by Stalwart."""
import json
import sys

from meilisearch_helpers import ensure_key, port_forward


def main():
    config = json.load(sys.stdin)
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        key = ensure_key(address, config["master_key"], config["key"])
    print(json.dumps({"key": key}))


if __name__ == "__main__":
    main()
