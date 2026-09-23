#!/usr/bin/env python3
"""Raise and resolve a temporary Zabbix problem and verify both inbox messages."""
import json
import socket
import struct
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "logging"))
from alert_delivery_helpers import matching_message_count
from api_helpers import ZabbixAPI


def main():
    config = json.load(sys.stdin)
    token = api_call(config, "user.login", {
        "username": config["username"],
        "password": config["password"],
        "userData": False,
    })
    api = ZabbixAPI(config["url"], token)
    host_rows = api.call("host.get", {
        "output": ["hostid", "host"],
        "filter": {"host": [config["host"]]},
    })
    if len(host_rows) != 1:
        raise RuntimeError("The managed Zabbix host was not found uniquely")
    host = host_rows[0]
    group_ids = {str(group["groupid"]) for group in api.call("host.get", {
        "output": ["hostid"],
        "hostids": [host["hostid"]],
        "selectGroups": ["groupid"],
    })[0].get("groups", [])}
    action_rows = api.call("action.get", {
        "output": "extend",
        "filter": {"name": ["Private cloud all warnings to Stalwart"]},
        "selectFilter": "extend",
        "selectOperations": "extend",
        "selectRecoveryOperations": "extend",
    })
    if len(action_rows) != 1 or str(action_rows[0].get("status")) != "0":
        raise RuntimeError("The managed Zabbix notification action is missing or disabled")
    conditions = action_rows[0].get("filter", {}).get("conditions", [])
    if not any(str(condition.get("conditiontype")) == "0" and str(condition.get("value")) in group_ids for condition in conditions):
        raise RuntimeError("The managed Zabbix notification action does not cover the monitored host group")
    if not any(str(condition.get("conditiontype")) == "4" and str(condition.get("operator")) == "5" and str(condition.get("value")) == "2" for condition in conditions):
        raise RuntimeError("The managed Zabbix notification action does not cover warning severity")
    operations = action_rows[0].get("operations", [])
    recovery_operations = action_rows[0].get("recovery_operations", [])
    if not operations or not recovery_operations:
        raise RuntimeError("The managed Zabbix notification action has no problem or recovery email operation")
    if not any("{EVENT.NAME}" in operation.get("opmessage", {}).get("subject", "") for operation in operations):
        raise RuntimeError("The managed Zabbix problem subject does not include the event name")
    if not any("{EVENT.NAME}" in operation.get("opmessage", {}).get("subject", "") for operation in recovery_operations):
        raise RuntimeError("The managed Zabbix recovery subject does not include the event name")
    users = api.call("user.get", {
        "output": ["userid", "username"],
        "filter": {"username": [config["username"]]},
        "selectMedias": "extend",
    })
    if len(users) != 1:
        raise RuntimeError("The configured Zabbix notification user was not found uniquely")
    user = users[0]
    if not any(
        config["recipient"] in (media.get("sendto") if isinstance(media.get("sendto"), list) else [media.get("sendto")])
        and str(media.get("active")) == "0"
        for media in user.get("medias", [])
    ):
        raise RuntimeError("The configured Zabbix notification user has no active media for the inbox")
    for operation in operations + recovery_operations:
        recipients = operation.get("opmessage_usr", [])
        if not any(str(recipient.get("userid")) == str(user["userid"]) for recipient in recipients):
            raise RuntimeError("The managed Zabbix action does not send both event types to the configured user")

    marker = "Private cloud alert validation " + uuid.uuid4().hex
    item_key = "private.cloud.validation.alert[" + uuid.uuid4().hex + "]"
    item_id = None
    trigger_id = None
    problem_may_be_active = False
    problem_resolved = False
    try:
        item_result = api.call("item.create", {
            "name": marker,
            "key_": item_key,
            "hostid": host["hostid"],
            "type": 2,
            "value_type": 3,
            "history": "1d",
            "status": 0,
        })
        item_id = item_result["itemids"][0]
        trigger_result = api.call("trigger.create", {
            "description": marker,
            "expression": "last(/" + config["host"] + "/" + item_key + ")=1",
            "priority": 2,
            "status": 0,
        })
        trigger_id = trigger_result["triggerids"][0]

        baseline = matching_message_count(config["mail"], marker)
        problem_may_be_active = True
        send_value(config["sender_address"], config["sender_port"], config["host"], item_key, "1")
        wait_for_messages(config["mail"], marker, baseline + 1)
        send_value(config["sender_address"], config["sender_port"], config["host"], item_key, "0")
        problem_resolved = True
        wait_for_messages(config["mail"], marker, baseline + 2)
        print(json.dumps({"problem_and_recovery_delivered": True, "marker": marker}, separators=(",", ":")))
    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_errors = []
        if item_id and problem_may_be_active and not problem_resolved:
            try:
                send_value(config["sender_address"], config["sender_port"], config["host"], item_key, "0")
            except Exception as error:
                cleanup_errors.append(error)
        try:
            trigger_ids = [trigger_id] if trigger_id else [
                trigger["triggerid"] for trigger in api.call("trigger.get", {
                    "output": ["triggerid"],
                    "filter": {"description": [marker]},
                    "hostids": [host["hostid"]],
                })
            ]
            if trigger_ids:
                api.call("trigger.delete", trigger_ids)
        except Exception as error:
            cleanup_errors.append(error)
        try:
            item_ids = [item_id] if item_id else [
                item["itemid"] for item in api.call("item.get", {
                    "output": ["itemid"],
                    "hostids": [host["hostid"]],
                    "filter": {"key_": [item_key]},
                })
            ]
            if item_ids:
                api.call("item.delete", item_ids)
        except Exception as error:
            cleanup_errors.append(error)
        if cleanup_errors:
            details = "; ".join(str(error) for error in cleanup_errors)
            if primary_exception:
                details = "Zabbix validation failed (" + str(primary_exception) + ") and cleanup also failed: " + details
            else:
                details = "Could not clean up all temporary Zabbix alert resources: " + details
            raise RuntimeError(details) from cleanup_errors[0]


def wait_for_messages(mail, marker, expected):
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if matching_message_count(mail, marker) >= expected:
            return
        time.sleep(10)
    raise RuntimeError("Zabbix did not deliver the expected problem and recovery messages: " + marker)


def send_value(address, port, host, key, value):
    body = json.dumps({
        "request": "sender data",
        "data": [{"host": host, "key": key, "value": value}],
    }, separators=(",", ":")).encode()
    packet = b"ZBXD\1" + struct.pack("<II", len(body), 0) + body
    with socket.create_connection((address, port), timeout=15) as connection:
        connection.settimeout(15)
        connection.sendall(packet)
        header = read_exact(connection, 13)
        if header[:5] != b"ZBXD\1":
            raise RuntimeError("Zabbix sender returned an invalid protocol header")
        length, _ = struct.unpack("<II", header[5:13])
        response = json.loads(read_exact(connection, length))
    if response.get("response") != "success" or "failed: 0" not in response.get("info", ""):
        raise RuntimeError("Zabbix rejected the synthetic alert value: " + response.get("info", "unknown error"))


def read_exact(connection, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise RuntimeError("Zabbix closed the sender connection early")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def api_call(config, method, params):
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    request = urllib.request.Request(config["url"], data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result or "result" not in result:
        raise RuntimeError("Zabbix API rejected " + method + ": " + result.get("error", {}).get("message", "missing result"))
    return result["result"]


if __name__ == "__main__":
    main()
