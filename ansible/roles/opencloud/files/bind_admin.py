#!/usr/bin/env python3
"""Give the built-in OpenCloud administrator the Stalwart address that signs in as it."""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from admin_bootstrap_helpers import opencloud_app_token, port_forward, request_json  # noqa: E402


def main():
    config = json.load(sys.stdin)
    token = opencloud_app_token(config["kubeconfig"], config["namespace"], "deployment/" + config["service"], config["admin_username"], "10m")
    headers = {"Authorization": "Basic " + base64.b64encode(f"{config['admin_username']}:{token}".encode()).decode()}
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        admin = request_json(address, "GET", "/graph/v1.0/me", headers=headers, name="OpenCloud")
        if admin.get("mail") == config["email"]:
            print(json.dumps({"changed": False}))
            return
        request_json(
            address, "PATCH", "/graph/v1.0/users/" + admin["id"], {"mail": config["email"]},
            allowed=(200, 204), headers=headers, name="OpenCloud",
        )
    print(json.dumps({"changed": True}))


if __name__ == "__main__":
    main()
