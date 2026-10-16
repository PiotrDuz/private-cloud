#!/usr/bin/env python3
"""Create the first AFFiNE administrator when the instance is unclaimed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from admin_bootstrap_helpers import port_forward, request_json  # noqa: E402

INITIALIZED_QUERY = {"query": "{ serverConfig { initialized } }"}


def main():
    config = json.load(sys.stdin)
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        server = request_json(address, "POST", "/graphql", INITIALIZED_QUERY, name="AFFiNE")
        if server["data"]["serverConfig"]["initialized"]:
            print(json.dumps({"changed": False}))
            return
        request_json(
            address, "POST", "/api/setup/create-admin-user",
            {"email": config["email"], "password": config["password"]},
            allowed=(200, 201), name="AFFiNE",
        )
    print(json.dumps({"changed": True}))


if __name__ == "__main__":
    main()
