#!/usr/bin/env python3
"""Converge SMTP media and Warning-or-higher notifications."""
import json
import sys
from api_helpers import ZabbixAPI
from notification_helpers import configure_email, configure_health


def main():
    configuration = json.load(sys.stdin)
    api = ZabbixAPI(configuration["url"], configuration["token"])
    if configuration["notifications"]:
        configure_email(api, configuration)
    else:
        actions = api.call("action.get", {"output": ["actionid", "status"], "filter": {"name": ["Private cloud all warnings to Stalwart"]}})
        for action in actions:
            if action["status"] != "1":
                api.call("action.update", {"actionid": action["actionid"], "status": 1})
                api.changed = True
    if configuration["logging"]:
        configure_health(api, configuration)
    print(json.dumps({"changed": api.changed, "status": "configured"}))


if __name__ == "__main__":
    main()
