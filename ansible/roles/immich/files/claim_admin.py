#!/usr/bin/env python3
"""Create the first Immich administrator when the instance is unclaimed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from admin_bootstrap_helpers import port_forward, request_json  # noqa: E402


def main():
    config = json.load(sys.stdin)
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        server = request_json(address, "GET", "/api/server/config", name="Immich")
        if server["isInitialized"]:
            print(json.dumps({"changed": False}))
            return
        request_json(
            address, "POST", "/api/auth/admin-sign-up",
            {"email": config["email"], "password": config["password"], "name": "Administrator"},
            allowed=(200, 201), name="Immich",
        )
    print(json.dumps({"changed": True}))


if __name__ == "__main__":
    main()
