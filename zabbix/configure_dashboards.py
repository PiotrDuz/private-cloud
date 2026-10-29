#!/usr/bin/env python3
"""Converge the managed Private cloud dashboard from the host's live items."""
import json
import sys
from api_helpers import ZabbixAPI
from dashboard_helpers import Items, dataset_capacity_page, disks_page, overview_page, services_page, storage_page


def main():
    config = json.load(sys.stdin)
    api = ZabbixAPI(config["url"], config["token"])
    items = Items(api, config["host_id"])
    items.require(dataset_key(prefix, name) for name in config["datasets"] for prefix in ("zfs.dataset.used", "zfs.dataset.utilization"))
    pages = [
        overview_page(config, items),
        storage_page(config, items),
        dataset_capacity_page(config, items),
        disks_page(config),
    ]
    if config["health"]:
        pages.append(services_page(config))
    dashboard = {"name": config["dashboard"], "private": 0, "display_period": 30, "auto_start": 0, "pages": pages}
    api.ensure("dashboard", "dashboardid", dashboard, {"output": "extend", "selectPages": "extend", "filter": {"name": [config["dashboard"]]}})
    print(json.dumps({"changed": api.changed, "status": "configured"}))


def dataset_key(prefix, name):
    return prefix + '["' + name + '"]'


if __name__ == "__main__":
    main()
