#!/usr/bin/env python3
"""Verify the managed OpenObserve alert rules and notification destination."""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2] / "roles" / "logging" / "files"))
from openobserve_helpers import OpenObserve, alert_definitions, contains, destination_definition, template_definition


def main():
    config = json.load(sys.stdin)
    client = OpenObserve(config["endpoint"], config["username"], config["password"])
    existing = client.named_alerts()
    if config["notifications"]:
        template, _ = client.request("GET", "/api/default/alerts/templates/private-cloud-email")
        destination, _ = client.request("GET", "/api/default/alerts/destinations/private-cloud-email")
        if not contains(template, template_definition()):
            raise RuntimeError("The managed OpenObserve email template does not match the desired configuration")
        if not contains(destination, destination_definition(config["recipient"])):
            raise RuntimeError("The managed OpenObserve email destination does not match the configured recipient")

    for alert in alert_definitions(config["notifications"]):
        alert_id = existing.get(alert["name"])
        if not alert_id:
            if config["notifications"]:
                raise RuntimeError("The managed OpenObserve alert is missing: " + alert["name"])
            continue
        current, _ = client.request("GET", "/api/v2/default/alerts/" + alert_id)
        if config["notifications"] and not contains(current, alert):
            raise RuntimeError("The managed OpenObserve alert differs from its desired configuration: " + alert["name"])
        if not config["notifications"] and current.get("enabled") is not False:
            raise RuntimeError("A managed OpenObserve log alert remains enabled while notifications are disabled")
    print(json.dumps({"alerts": len(alert_definitions(config["notifications"])), "notifications": bool(config["notifications"]), "valid": True}, separators=(",", ":")))


if __name__ == "__main__":
    main()
