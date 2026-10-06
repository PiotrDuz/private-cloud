#!/usr/bin/env python3
"""Check the live Zabbix API, host templates, dashboard, and configured mail route."""
import json
import sys
import urllib.request


def main():
    config = json.load(sys.stdin)
    version = api_call(config["url"], "apiinfo.version", {}, token=None)
    if tuple(int(component) for component in version.split(".")[:2]) < (7, 4):
        raise RuntimeError("Zabbix server must be version 7.4 or newer")
    token = api_call(config["url"], "user.login", {
        "username": config["username"],
        "password": config["password"],
        "userData": False,
    }, token=None)
    try:
        api = lambda method, params: api_call(config["url"], method, params, token)
        host = require_one(api("host.get", {
            "output": ["hostid", "host", "name", "status", "tls_accept", "tls_connect"],
            "filter": {"host": [config["host"]]},
            "selectHostGroups": ["groupid"],
            "selectParentTemplates": ["templateid", "host"],
        }), "managed host")
        if host["host"] != config["host"] or host["name"] != config["host"] or str(host["status"]) != "0":
            raise RuntimeError("The configured Zabbix host is missing, renamed, or disabled")
        if str(host.get("tls_accept")) != "1" or str(host.get("tls_connect")) != "1":
            raise RuntimeError("The managed Zabbix host does not accept and use its configured TLS mode")

        group = require_one(api("hostgroup.get", {
            "output": ["groupid", "name"],
            "filter": {"name": [config["host_group"]]},
        }), "managed host group")
        group_ids = {str(entry["groupid"]) for entry in host.get("hostgroups", [])}
        if str(group["groupid"]) not in group_ids:
            raise RuntimeError("The managed Zabbix host is not linked to its configured group")

        templates = api("template.get", {
            "output": ["templateid", "host"],
            "filter": {"host": [name for choice in config["template_choices"] for name in choice]},
        })
        linked_template_ids = {str(entry["templateid"]) for entry in host.get("parentTemplates", [])}
        for choice in config["template_choices"]:
            choice_ids = {str(entry["templateid"]) for entry in templates if entry["host"] in choice}
            if not choice_ids or not linked_template_ids.intersection(choice_ids):
                raise RuntimeError("A required Zabbix template is absent or not linked to the managed host")

        dashboard = require_one(api("dashboard.get", {
            "output": ["dashboardid", "name"],
            "selectPages": "extend",
            "filter": {"name": [config["dashboard"]]},
        }), "managed storage dashboard")
        pages = dashboard.get("pages", [])
        capacity_pages = [page for page in pages if page.get("name") == "Dataset capacity"]
        if len(capacity_pages) != 1:
            raise RuntimeError("The managed Zabbix dashboard has no unique Dataset capacity page")
        widget_names = {widget.get("name") for widget in capacity_pages[0].get("widgets", [])}
        if widget_names != {"Leaf datasets by quota utilization", "Current leaf dataset allocation"}:
            raise RuntimeError("The managed Zabbix storage dashboard widgets are incomplete")
        utilization = next(widget for widget in capacity_pages[0]["widgets"] if widget.get("name") == "Leaf datasets by quota utilization")
        configured_datasets = {
            field.get("value") for field in utilization.get("fields", [])
            if str(field.get("name", "")).startswith("columns.0.items.")
        }
        expected_datasets = {"Dataset " + name + ": Utilization" for name in config["datasets"]}
        if not expected_datasets.issubset(configured_datasets):
            raise RuntimeError("The storage dashboard does not include every dataset enabled in the global configuration")

        if config["logging"]:
            validate_logging_items(api, host["hostid"], config["certificates"])
        if config["notifications"]:
            validate_notifications(api, config, group["groupid"])
        else:
            actions = api("action.get", {
                "output": ["actionid", "status"],
                "filter": {"name": ["Private cloud all warnings to Stalwart"]},
            })
            if any(str(action["status"]) == "0" for action in actions):
                raise RuntimeError("The managed Zabbix email action is still enabled while notifications are disabled")
        print(json.dumps({"host": config["host"], "version": version, "valid": True}, separators=(",", ":")))
    finally:
        try:
            api_call(config["url"], "user.logout", {}, token)
        except Exception:
            pass


def validate_logging_items(api, host_id, certificates):
    keys = ["observability.health"]
    for certificate in certificates:
        name = certificate["name"]
        keys.extend([
            'observability.certificate.valid["' + name + '"]',
            'observability.certificate.days["' + name + '"]',
        ])
    items = api("item.get", {
        "output": ["itemid", "key_"],
        "hostids": [host_id],
        "filter": {"key_": keys},
    })
    found = {item["key_"] for item in items}
    missing = set(keys) - found
    if missing:
        raise RuntimeError("Zabbix is missing configured Alloy or certificate health items")


def validate_notifications(api, config, group_id):
    relay = config["relay"]
    media_type = require_one(api("mediatype.get", {
        "output": "extend",
        "filter": {"name": ["Private cloud Stalwart inbox"]},
    }), "managed email media type")
    expected_media = {
        "type": "0",
        "status": "0",
        "smtp_server": relay["host"],
        "smtp_port": str(relay["port"]),
        "smtp_helo": config["mail_hostname"],
        "smtp_email": config["from_address"],
        "smtp_security": "2" if relay["implicit_tls"] else "1",
        "smtp_verify_peer": "1",
        "smtp_verify_host": "1",
        "smtp_authentication": "1",
        "username": relay["username"],
        "maxattempts": "10",
        "attempt_interval": "1m",
    }
    if any(str(media_type.get(key, "")) != value for key, value in expected_media.items()):
        raise RuntimeError("The Zabbix SMTP media type does not match the configured relay")

    user = require_one(api("user.get", {
        "output": ["userid", "username"],
        "filter": {"username": [config["username"]]},
        "selectMedias": "extend",
    }), "configured administrator")
    matching_media = [
        entry for entry in user.get("medias", [])
        if str(entry.get("mediatypeid")) == str(media_type["mediatypeid"])
    ]
    if not any(
        config["recipient"] in (entry.get("sendto") if isinstance(entry.get("sendto"), list) else [entry.get("sendto")])
        and str(entry.get("active")) == "0"
        for entry in matching_media
    ):
        raise RuntimeError("The configured Zabbix administrator has no active media for the Stalwart recipient")

    action = require_one(api("action.get", {
        "output": "extend",
        "filter": {"name": ["Private cloud all warnings to Stalwart"]},
        "selectFilter": "extend",
        "selectOperations": "extend",
        "selectRecoveryOperations": "extend",
    }), "managed notification action")
    if str(action.get("status")) != "0" or str(action.get("esc_period")) != "1h" or str(action.get("pause_suppressed")) != "1":
        raise RuntimeError("The managed Zabbix notification action is disabled or has incorrect reminder behavior")
    conditions = action.get("filter", {}).get("conditions", [])
    if not any(str(item.get("conditiontype")) == "0" and str(item.get("value")) == str(group_id) for item in conditions):
        raise RuntimeError("The managed Zabbix action does not cover the configured host group")
    if not any(str(item.get("conditiontype")) == "4" and str(item.get("operator")) == "5" and str(item.get("value")) == "2" for item in conditions):
        raise RuntimeError("The managed Zabbix action does not cover Warning-or-higher problems")
    for operation_name in ("operations", "recovery_operations"):
        operations = action.get(operation_name, [])
        if not any(
            any(str(recipient.get("userid")) == str(user["userid"]) for recipient in operation.get("opmessage_usr", []))
            for operation in operations
        ):
            raise RuntimeError("The managed Zabbix action has no configured problem or recovery email operation")


def require_one(rows, description):
    if len(rows) != 1:
        raise RuntimeError("Expected exactly one " + description)
    return rows[0]


def api_call(url, method, parameters, token=None):
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": parameters, "id": 1}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result or "result" not in result:
        raise RuntimeError("Zabbix API rejected " + method + ": " + result.get("error", {}).get("message", "missing result"))
    return result["result"]


if __name__ == "__main__":
    main()
