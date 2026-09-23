#!/usr/bin/env python3
"""Exercise the configured OpenObserve alert destination and verify inbox delivery."""
import json
import sys
import time
import uuid

from alert_delivery_helpers import wait_for_delivery
from openobserve_helpers import OpenObserve, conditions


def main():
    config = json.load(sys.stdin)
    client = OpenObserve(config["endpoint"], config["username"], config["password"])
    marker = "private_cloud_validation_" + uuid.uuid4().hex
    alert_id = None
    try:
        definition = {
            "name": marker,
            "org_id": "default",
            "stream_type": "logs",
            "stream_name": "logs",
            "is_real_time": True,
            "query_condition": {
                "type": "custom",
                "conditions": conditions(("service", "=", marker)),
            },
            "trigger_condition": {
                "period": 1,
                "operator": ">=",
                "threshold": 1,
                "frequency": 1,
                "frequency_type": "minutes",
                "silence": 0,
            },
            "destinations": ["private-cloud-email"],
            "row_template": "[{severity}] {namespace}/{service}: {message}",
            "description": "Temporary private cloud alert delivery validation.",
            "enabled": True,
            "tz_offset": 0,
        }
        created, _ = client.request("POST", "/api/v2/default/alerts", definition)
        alert_id = response_alert_id(created)
        if not alert_id:
            alert_id = client.named_alerts().get(marker)
        if not alert_id:
            raise RuntimeError("OpenObserve did not return the temporary alert ID")

        now = int(time.time())
        client.request(
            "POST",
            "/api/default/logs/_json",
            [{
                "_timestamp": now * 1_000_000,
                "service": marker,
                "severity": "critical",
                "namespace": "validation",
                "message": marker,
            }],
        )
        if not wait_for_delivery(config["mail"], marker):
            raise RuntimeError("OpenObserve alert did not reach the Stalwart inbox: " + marker)
        print(json.dumps({"delivered": True, "marker": marker}, separators=(",", ":")))
    finally:
        primary_exception = sys.exc_info()[1]
        try:
            if not alert_id:
                alert_id = client.named_alerts().get(marker)
            if alert_id:
                client.request(
                    "DELETE",
                    "/api/v2/default/alerts/" + alert_id,
                    allowed=(200, 204, 404),
                )
        except Exception as error:
            if primary_exception:
                raise RuntimeError("OpenObserve validation failed and its temporary alert could not be removed: " + str(primary_exception)) from error
            raise


def response_alert_id(response):
    if isinstance(response, dict):
        for key in ("alert_id", "id"):
            value = response.get(key)
            if isinstance(value, str):
                return value
        for value in response.values():
            found = response_alert_id(value)
            if found:
                return found
    elif isinstance(response, list):
        for value in response:
            found = response_alert_id(value)
            if found:
                return found
    return None


if __name__ == "__main__":
    main()
