from __future__ import annotations

import json
import re
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Sequence

from installer_helpers import InstallerError

HOST_GROUP = "Private cloud"
STORAGE_DASHBOARD = "Private cloud ZFS storage"
DEFAULT_ADMIN_USERNAME = "Admin"
DEFAULT_ADMIN_PASSWORD = "zabbix"
LOGIN_BLOCK_SECONDS = 31
TEMPLATE_CHOICES = (
    ("Linux by Zabbix agent active",),
    ("SMART by Zabbix agent active 2", "SMART by Zabbix agent 2 active"),
    ("ZFS by Zabbix agent active",),
    ("Memory ECC by Zabbix agent active",),
)
LEAF_ITEMS = (
    ("config", 'zfs.dataset.used["config"]', 'zfs.dataset.utilization["config"]'),
    ("images", 'zfs.dataset.used["images"]', 'zfs.dataset.utilization["images"]'),
    (
        "ephemeral",
        'zfs.dataset.used["ephemeral"]',
        'zfs.dataset.utilization["ephemeral"]',
    ),
    (
        "postgres",
        'zfs.dataset.used["postgres"]',
        'zfs.dataset.utilization["postgres"]',
    ),
    ("zabbix", 'zfs.dataset.used["zabbix"]', 'zfs.dataset.utilization["zabbix"]'),
)


def validate_template(template_path: Path) -> None:
    read_template_source(template_path)


def read_template_source(template_path: Path) -> str:
    try:
        source = template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise InstallerError(f"Cannot read Zabbix template: {template_path}") from error

    values = re.findall(
        r"^\s*- uuid: (\S+)",
        source,
        re.MULTILINE,
    )
    if not values:
        raise InstallerError(f"Zabbix template contains no UUIDs: {template_path}")
    if len(values) != len(set(values)):
        raise InstallerError(f"Zabbix template contains duplicate UUIDs: {template_path}")
    for value in values:
        if re.fullmatch(r"[0-9a-f]{32}", value) is None:
            raise InstallerError(
                f"Zabbix template contains an invalid UUID: {template_path}: {value}"
            )
        parsed = uuid.UUID(hex=value)
        if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
            raise InstallerError(
                f"Zabbix template UUID is not UUIDv4: {template_path}: {value}"
            )
    return source


def configure_monitored_host(
    api_url: str,
    username: str,
    password: str,
    hostname: str,
    template_paths: Sequence[Path],
) -> dict[str, Any]:
    api = ZabbixApi(api_url)
    wait_for_api(api)
    try:
        login_or_bootstrap_admin(api, username, password)
        for template_path in template_paths:
            import_template(api, template_path)
        group_id = ensure_host_group(api, HOST_GROUP)
        templates = resolve_templates(api, TEMPLATE_CHOICES)
        host_id = ensure_host(api, hostname, group_id, templates)
        dashboard_id = ensure_storage_dashboard(api, host_id)
    finally:
        api.logout()

    return {
        "api_url": api_url,
        "group": HOST_GROUP,
        "host": hostname,
        "host_id": host_id,
        "dashboard": STORAGE_DASHBOARD,
        "dashboard_id": dashboard_id,
        "templates": list(templates),
    }


def login_or_bootstrap_admin(
    api: ZabbixApi,
    username: str,
    password: str,
) -> None:
    login_credentials = (
        (username, password, False),
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, True),
    )
    used_bootstrap = try_login_credentials(api, login_credentials)
    if used_bootstrap is None:
        for credentials in login_credentials:
            time.sleep(LOGIN_BLOCK_SECONDS)
            used_bootstrap = try_login_credentials(api, (credentials,))
            if used_bootstrap is not None:
                break
    if used_bootstrap is None:
        raise InstallerError(
            "Zabbix administrator login failed with both configured and initial credentials"
        )
    if not used_bootstrap:
        return
    if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD:
        return

    api.update_current_user(
        username,
        password,
        current_password=DEFAULT_ADMIN_PASSWORD,
    )
    api.logout()
    api.login(username, password)


def try_login_credentials(
    api: ZabbixApi,
    credentials: Sequence[tuple[str, str, bool]],
) -> bool | None:
    for username, password, is_bootstrap in credentials:
        try:
            api.login(username, password)
        except ZabbixApiError as error:
            if error.method != "user.login" or not error.is_login_rejection():
                raise
            continue
        return is_bootstrap
    return None


def wait_for_api(api: ZabbixApi) -> None:
    last_error: InstallerError | None = None
    for _ in range(60):
        try:
            api.call("apiinfo.version", {}, authenticated=False)
            return
        except InstallerError as error:
            last_error = error
            time.sleep(5)
    raise InstallerError(f"Zabbix API did not become ready: {last_error}")


def import_template(api: ZabbixApi, template_path: Path) -> None:
    source = read_template_source(template_path)
    api.call(
        "configuration.import",
        {
            "format": "yaml",
            "source": source,
            "rules": {
                "discoveryRules": managed_import_rule(),
                "graphs": managed_import_rule(),
                "items": managed_import_rule(),
                "template_groups": import_rule(),
                "templates": import_rule(),
                "triggers": managed_import_rule(),
                "valueMaps": managed_import_rule(),
            },
        },
    )


def ensure_host_group(api: ZabbixApi, name: str) -> str:
    groups = api.call(
        "hostgroup.get",
        {"output": ["groupid", "name"], "filter": {"name": [name]}},
    )
    if groups:
        return str(groups[0]["groupid"])
    result = api.call("hostgroup.create", {"name": name})
    return str(result["groupids"][0])


def resolve_templates(
    api: ZabbixApi,
    choices: Sequence[Sequence[str]],
) -> dict[str, str]:
    names = [name for alternatives in choices for name in alternatives]
    templates = api.call(
        "template.get",
        {
            "output": ["templateid", "host"],
            "filter": {"host": names},
        },
    )
    available = {str(item["host"]): str(item["templateid"]) for item in templates}
    resolved: dict[str, str] = {}
    for alternatives in choices:
        selected = next((name for name in alternatives if name in available), None)
        if selected is None:
            raise InstallerError(
                f"Required Zabbix template is unavailable: {' or '.join(alternatives)}"
            )
        resolved[selected] = available[selected]
    return resolved


def ensure_host(
    api: ZabbixApi,
    hostname: str,
    group_id: str,
    templates: dict[str, str],
) -> str:
    hosts = api.call(
        "host.get",
        {
            "output": ["hostid", "host"],
            "filter": {"host": [hostname]},
        },
    )
    if hosts:
        host_id = str(hosts[0]["hostid"])
        api.call(
            "host.update",
            {
                "hostid": host_id,
                "status": 0,
                "tls_accept": 1,
                "tls_connect": 1,
            },
        )
        api.call(
            "host.massadd",
            {
                "groups": [{"groupid": group_id}],
                "hosts": [{"hostid": host_id}],
                "templates": [
                    {"templateid": template_id}
                    for template_id in templates.values()
                ],
            },
        )
        return host_id

    result = api.call(
        "host.create",
        {
            "groups": [{"groupid": group_id}],
            "host": hostname,
            "name": hostname,
            "status": 0,
            "templates": [
                {"templateid": template_id}
                for template_id in templates.values()
            ],
            "tls_accept": 1,
            "tls_connect": 1,
        },
    )
    return str(result["hostids"][0])


def ensure_storage_dashboard(api: ZabbixApi, host_id: str) -> str:
    items = resolve_host_items(api, host_id)
    pages = [
        {
            "name": "Dataset capacity",
            "widgets": [
                dataset_utilization_widget(host_id),
                dataset_allocation_widget(items),
            ],
        }
    ]
    dashboards = api.call(
        "dashboard.get",
        {
            "output": ["dashboardid", "name"],
            "filter": {"name": [STORAGE_DASHBOARD]},
        },
    )
    if dashboards:
        dashboard_id = str(dashboards[0]["dashboardid"])
        api.call(
            "dashboard.update",
            {
                "dashboardid": dashboard_id,
                "name": STORAGE_DASHBOARD,
                "display_period": 30,
                "auto_start": 0,
                "pages": pages,
            },
        )
        return dashboard_id

    result = api.call(
        "dashboard.create",
        {
            "name": STORAGE_DASHBOARD,
            "private": 0,
            "display_period": 30,
            "auto_start": 0,
            "pages": pages,
        },
    )
    return str(result["dashboardids"][0])


def resolve_host_items(api: ZabbixApi, host_id: str) -> dict[str, str]:
    required_keys = [
        key
        for _, used_key, percent_key in LEAF_ITEMS
        for key in (used_key, percent_key)
    ]
    records = api.call(
        "item.get",
        {
            "output": ["itemid", "key_", "name"],
            "hostids": [host_id],
            "filter": {"key_": required_keys},
        },
    )
    items = {str(record["key_"]): str(record["itemid"]) for record in records}
    missing = [key for key in required_keys if key not in items]
    if missing:
        raise InstallerError(
            f"Dashboard items are unavailable on the monitored host: {', '.join(missing)}"
        )
    return items


def dataset_utilization_widget(host_id: str) -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        {"type": 3, "name": "hostids.0", "value": host_id},
        {"type": 0, "name": "layout", "value": 1},
        {"type": 0, "name": "show_problems", "value": 1},
        {"type": 0, "name": "item_ordering_order_by", "value": 3},
        {"type": 0, "name": "item_ordering_order", "value": 2},
        {"type": 0, "name": "item_ordering_limit", "value": len(LEAF_ITEMS)},
        {"type": 0, "name": "columns.0.display", "value": 2},
        {"type": 1, "name": "columns.0.min", "value": "0"},
        {"type": 1, "name": "columns.0.max", "value": "100"},
        {"type": 1, "name": "columns.0.base_color", "value": "42A5F5"},
        {
            "type": 1,
            "name": "columns.0.thresholds.0.color",
            "value": "FFB300",
        },
        {"type": 1, "name": "columns.0.thresholds.0.threshold", "value": "80"},
        {
            "type": 1,
            "name": "columns.0.thresholds.1.color",
            "value": "E53935",
        },
        {"type": 1, "name": "columns.0.thresholds.1.threshold", "value": "90"},
        {"type": 0, "name": "columns.0.decimal_places", "value": 1},
    ]
    for index, (label, _, _) in enumerate(LEAF_ITEMS):
        fields.append(
            {
                "type": 1,
                "name": f"columns.0.items.{index}",
                "value": f"Dataset {label}: Utilization",
            }
        )
    return {
        "type": "topitems",
        "name": "Leaf datasets by quota utilization",
        "x": 0,
        "y": 0,
        "width": 36,
        "height": 8,
        "view_mode": 0,
        "fields": fields,
    }


def dataset_allocation_widget(items: dict[str, str]) -> dict[str, Any]:
    colors = ("42A5F5", "66BB6A", "FFA726", "AB47BC", "EF5350")
    fields: list[dict[str, Any]] = [
        {"type": 0, "name": "ds.0.dataset_type", "value": 0},
        {"type": 0, "name": "draw_type", "value": 0},
        {"type": 0, "name": "legend", "value": 1},
        {"type": 0, "name": "legend_value", "value": 1},
        {"type": 0, "name": "legend_lines_mode", "value": 1},
        {"type": 0, "name": "legend_lines", "value": len(LEAF_ITEMS)},
    ]
    for index, (_, used_key, _) in enumerate(LEAF_ITEMS):
        fields.extend(
            (
                {
                    "type": 4,
                    "name": f"ds.0.itemids.{index}",
                    "value": items[used_key],
                },
                {
                    "type": 1,
                    "name": f"ds.0.color.{index}",
                    "value": colors[index],
                },
                {"type": 0, "name": f"ds.0.type.{index}", "value": 0},
            )
        )
    return {
        "type": "piechart",
        "name": "Current leaf dataset allocation",
        "x": 36,
        "y": 0,
        "width": 36,
        "height": 8,
        "view_mode": 0,
        "fields": fields,
    }


def import_rule() -> dict[str, bool]:
    return {
        "createMissing": True,
        "updateExisting": True,
    }


def managed_import_rule() -> dict[str, bool]:
    return {
        "createMissing": True,
        "updateExisting": True,
        "deleteMissing": True,
    }


class ZabbixApi:
    def __init__(self, url: str) -> None:
        self.url = url
        self.token: str | None = None
        self.user_id: str | None = None
        self.request_id = 0

    def login(self, username: str, password: str) -> None:
        user_data = self.call(
            "user.login",
            {"username": username, "password": password, "userData": True},
            authenticated=False,
        )
        if not isinstance(user_data, dict):
            raise InstallerError("Zabbix API returned invalid authenticated user data")
        token = user_data.get("sessionid")
        user_id = user_data.get("userid")
        if not isinstance(token, str) or not token:
            raise InstallerError("Zabbix API returned invalid authenticated user data")
        if not isinstance(user_id, str) or not user_id:
            raise InstallerError("Zabbix API returned invalid authenticated user data")
        self.token = token
        self.user_id = user_id

    def update_current_user(
        self,
        username: str,
        password: str,
        *,
        current_password: str,
    ) -> None:
        if self.user_id is None:
            raise InstallerError("Zabbix API authenticated user ID is unavailable")
        self.call(
            "user.update",
            {
                "userid": self.user_id,
                "username": username,
                "passwd": password,
                "current_passwd": current_password,
            },
        )

    def logout(self) -> None:
        if self.token is None:
            return
        try:
            self.call("user.logout", {})
        except InstallerError:
            pass
        finally:
            self.token = None
            self.user_id = None

    def call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        authenticated: bool = True,
    ) -> Any:
        if authenticated and self.token is None:
            raise InstallerError("Zabbix API authentication is required")
        self.request_id += 1
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self.request_id,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json-rpc"}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstallerError(f"Zabbix API request failed: {method}") from error
        if "error" in result:
            error = result["error"]
            detail = error.get("data") or error.get("message") or "unknown error"
            raise ZabbixApiError(method, str(detail))
        if "result" not in result:
            raise InstallerError(f"Zabbix API returned no result for {method}")
        return result["result"]


class ZabbixApiError(InstallerError):
    def __init__(self, method: str, detail: str) -> None:
        super().__init__(f"Zabbix API {method} failed: {detail}")
        self.method = method
        self.detail = detail

    def is_login_rejection(self) -> bool:
        return "incorrect user name or password" in self.detail.lower()
