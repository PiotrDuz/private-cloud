"""Small OpenObserve API client and managed alert definitions."""
import base64
import json
import urllib.error
import urllib.parse
import urllib.request


def alert_definitions(enabled):
    definitions = []
    for level in ("warn", "error", "critical"):
        definitions.append(alert_definition(
            "private_cloud_" + level,
            severity_filter(level),
            ">=",
            1,
            1,
            "Notify when a non-OpenObserve service emits a " + level + " log.",
            enabled,
        ))
    definitions.append(alert_definition(
        "private_cloud_heartbeat_missing",
        conditions(("service", "=", "private-cloud-log-heartbeat.service")),
        "<",
        1,
        1,
        "Notify when the host logging heartbeat is absent.",
        enabled,
    ))
    return definitions


def template_definition():
    return {
        "name": "private-cloud-email",
        "type": "email",
        "title": "[private-cloud] {alert_name}",
        "body": "Alert {alert_name} matched {alert_count} rows in {stream_name}.\n\n{rows}\n\n{alert_url}",
    }


def destination_definition(recipient):
    return {
        "name": "private-cloud-email",
        "type": "email",
        "emails": [recipient],
        "template": "private-cloud-email",
    }


def alert_definition(name, filters, operator, threshold, frequency, description, enabled):
    return {
        "name": name,
        "org_id": "default",
        "stream_type": "logs",
        "stream_name": "logs",
        "is_real_time": False,
        "query_condition": {"type": "custom", "conditions": filters},
        "trigger_condition": {
            "period": 5,
            "operator": operator,
            "threshold": threshold,
            "frequency": frequency,
            "frequency_type": "minutes",
            "silence": 5,
        },
        "destinations": ["private-cloud-email"],
        "row_template": "[{severity}] {namespace}/{service}: {message}",
        "description": description,
        "enabled": enabled,
        "tz_offset": 0,
    }


def severity_filter(level):
    return conditions(("severity", "=", level), ("service", "!=", "openobserve"))


def conditions(*entries):
    return {
        "version": 2,
        "conditions": {
            "filterType": "group",
            "logicalOperator": "AND",
            "conditions": [
                {
                    "filterType": "condition",
                    "column": column,
                    "operator": operator,
                    "value": value,
                    "ignore_case": False,
                    "logicalOperator": "AND",
                }
                for column, operator, value in entries
            ],
        },
    }


def contains(current, desired):
    if isinstance(desired, dict):
        return isinstance(current, dict) and all(key in current and contains(current[key], value) for key, value in desired.items())
    if isinstance(desired, list):
        return isinstance(current, list) and current == desired
    return current == desired


def collect_alerts(value, found):
    if isinstance(value, dict):
        alert_id = value.get("alert_id", value.get("id"))
        if isinstance(value.get("name"), str) and isinstance(alert_id, str):
            found[value["name"]] = alert_id
        for child in value.values():
            collect_alerts(child, found)
    elif isinstance(value, list):
        for child in value:
            collect_alerts(child, found)


class OpenObserve:
    def __init__(self, endpoint, username, password):
        self.endpoint = endpoint.rstrip("/")
        token = base64.b64encode((username + ":" + password).encode()).decode()
        self.headers = {"Authorization": "Basic " + token, "Content-Type": "application/json", "User-Agent": "private-cloud-provisioner"}

    def upsert_named(self, collection, name, desired):
        path = collection + "/" + urllib.parse.quote(name, safe="")
        current, status = self.request("GET", path, allowed=(200, 404))
        if status == 200 and contains(current, desired):
            return False
        self.request("PUT" if status == 200 else "POST", path if status == 200 else collection, desired)
        return True

    def named_alerts(self):
        response, _ = self.request("GET", "/api/v2/default/alerts?page_size=1000")
        found = {}
        collect_alerts(response, found)
        return found

    def upsert_alert(self, alert_id, desired):
        if alert_id:
            path = "/api/v2/default/alerts/" + urllib.parse.quote(alert_id, safe="")
            current, _ = self.request("GET", path)
            if contains(current, desired):
                return False
            self.request("PUT", path, desired)
        else:
            self.request("POST", "/api/v2/default/alerts", desired)
        return True

    def disable_alerts(self, existing, names):
        changed = False
        for name in names:
            alert_id = existing.get(name)
            if not alert_id:
                continue
            path = "/api/v2/default/alerts/" + urllib.parse.quote(alert_id, safe="")
            current, _ = self.request("GET", path)
            if current.get("enabled") is False:
                continue
            current["enabled"] = False
            self.request("PUT", path, current)
            changed = True
        return changed

    def request(self, method, path, body=None, allowed=(200,)):
        data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = urllib.request.Request(self.endpoint + path, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024)
                return (json.loads(raw) if raw else {}, response.status)
        except urllib.error.HTTPError as error:
            if error.code in allowed:
                raw = error.read(8 * 1024 * 1024)
                return (json.loads(raw) if raw else {}, error.code)
            details = error.read(64 * 1024).decode(errors="replace")
            raise RuntimeError(f"OpenObserve {method} {path} failed with HTTP {error.code}: {details}") from error
