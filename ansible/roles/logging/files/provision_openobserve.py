#!/usr/bin/env python3
"""Provision the managed OpenObserve email destination and log alerts."""
import json
import sys

from openobserve_helpers import OpenObserve, alert_definitions, destination_definition, template_definition


def main():
    config = json.load(sys.stdin)
    client = OpenObserve(config['endpoint'], config['username'], config['password'])
    enabled = config['notifications']
    existing = client.named_alerts()
    if not enabled:
        changed = client.disable_alerts(existing, [alert["name"] for alert in alert_definitions(False)])
        print(json.dumps({"changed": changed}, separators=(",", ":")))
        return
    changed = client.upsert_named("/api/default/alerts/templates", "private-cloud-email", template_definition())
    changed |= client.upsert_named("/api/default/alerts/destinations", "private-cloud-email", destination_definition(config['recipient']))
    for alert in alert_definitions(enabled):
        changed |= client.upsert_alert(existing.get(alert["name"]), alert)
    print(json.dumps({"changed": changed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
