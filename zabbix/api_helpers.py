"""Small JSON-RPC client for managed Zabbix objects."""
import json
import urllib.request


def same(actual, desired):
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(key in actual and same(actual[key], value) for key, value in desired.items())
    if isinstance(desired, list):
        return isinstance(actual, list) and len(actual) == len(desired) and all(any(same(candidate, value) for candidate in actual) for value in desired)
    return str(actual) == str(desired)


class ZabbixAPI:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.changed = False

    def call(self, method, parameters):
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": parameters, "id": 1}).encode()
        request = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        if "error" in result or "result" not in result:
            raise RuntimeError("Zabbix API rejected " + method + ": " + result.get("error", {}).get("message", "missing result"))
        return result["result"]

    def ensure(self, resource, identifier, desired, query, force=False):
        existing = self.call(resource + ".get", query)
        if len(existing) > 1:
            raise RuntimeError("Multiple managed " + resource + " objects matched")
        if existing:
            object_id = existing[0][identifier]
            if force or not same(existing[0], desired):
                self.call(resource + ".update", {identifier: object_id, **desired})
                self.changed = True
            return object_id
        result = self.call(resource + ".create", desired)
        self.changed = True
        return result[identifier + "s"][0]
