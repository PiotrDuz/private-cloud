#!/usr/bin/env python3
"""Complete the Jellyfin startup wizard with the installer-managed administrator."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from admin_bootstrap_helpers import port_forward, request_json  # noqa: E402


def main():
    config = json.load(sys.stdin)
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        server = request_json(address, "GET", "/System/Info/Public", name="Jellyfin")
        if server["StartupWizardCompleted"]:
            print(json.dumps({"changed": False}))
            return
        request_json(address, "GET", "/Startup/User", name="Jellyfin")
        request_json(
            address, "POST", "/Startup/User",
            {"Name": config["username"], "Password": config["password"]},
            allowed=(204,), name="Jellyfin",
        )
        request_json(address, "POST", "/Startup/Complete", allowed=(204,), name="Jellyfin")
    print(json.dumps({"changed": True}))


if __name__ == "__main__":
    main()
