"""Bounded OpenObserve, Alloy, and TLS probes."""
import base64
import concurrent.futures
import json
import re
import smtplib
import socket
import ssl
import time
import urllib.request


def collect_pipeline(configuration):
    endpoints = configuration["endpoints"]
    paths = {
        "openobserve_up": endpoints["openobserve"] + "/healthz",
        "alloy_up": endpoints["alloy"] + "/-/healthy",
        "openobserve_metrics": endpoints["openobserve"] + "/metrics",
        "alloy_metrics": endpoints["alloy"] + "/metrics",
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        requests = {name: executor.submit(read_url, url) for name, url in paths.items()}
        data = {name: future.result() for name, future in requests.items()}
    result = {name: int(data[name] is not None) for name in ("openobserve_up", "alloy_up")}
    result["heartbeat"] = search_count(
        endpoints["openobserve"], configuration["credentials"],
        "service = 'private-cloud-log-heartbeat.service'",
    )
    result["openobserve_internal_warnings"] = search_count(
        endpoints["openobserve"], configuration["credentials"],
        "service = 'openobserve' AND level IN ('warn', 'error', 'critical')",
    )
    result["metrics_up"] = int(data["openobserve_metrics"] is not None and data["alloy_metrics"] is not None)
    for key, source, metric in (
        ("alloy_retries", "alloy", "loki_write_batch_retries_total"),
        ("alloy_dropped", "alloy", "loki_write_dropped_entries_total"),
        ("openobserve_ingest_errors", "openobserve", "zo_ingest_errors"),
        ("openobserve_notifications_failed", "openobserve", "zo_alert_grouping_send_errors_total"),
    ):
        result[key] = sum_metric(data[source + "_metrics"] or "", metric)
    return result


def search_count(endpoint, credentials, predicate):
    now = int(time.time() * 1_000_000)
    body = {
        "query": {
            "sql": 'SELECT count(*) AS count FROM "logs" WHERE ' + predicate,
            "start_time": now - 300_000_000,
            "end_time": now,
            "from": 0,
            "size": 1,
        }
    }
    authentication = base64.b64encode((credentials["username"] + ":" + credentials["password"]).encode()).decode()
    data = read_url(endpoint + "/api/default/_search", json.dumps(body).encode(), {"Authorization": "Basic " + authentication, "Content-Type": "application/json"})
    try:
        return int(float(json.loads(data)["hits"][0]["count"]))
    except (ValueError, TypeError, KeyError, IndexError):
        return 0


def certificate_health(address, certificate):
    try:
        context = ssl.create_default_context()
        if certificate["protocol"] == "smtp":
            with smtplib.SMTP(timeout=3) as client:
                client._host = certificate["hostname"]
                client.connect(address, 25)
                client.ehlo()
                client.starttls(context=context)
                peer = client.sock.getpeercert()
        else:
            with socket.create_connection((address, 443), timeout=3) as connection:
                with context.wrap_socket(connection, server_hostname=certificate["hostname"]) as secured:
                    peer = secured.getpeercert()
        return {"valid": 1, "days": (ssl.cert_time_to_seconds(peer["notAfter"]) - time.time()) / 86400}
    except (OSError, smtplib.SMTPException, ValueError, KeyError):
        return {"valid": 0, "days": 0}


def read_url(url, data=None, headers=None):
    try:
        request_headers = {"User-Agent": "private-cloud-health"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers)
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status < 200 or response.status >= 300:
                return None
            return response.read(8 * 1024 * 1024).decode()
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def sum_metric(text, name):
    pattern = re.compile(r"^" + re.escape(name) + r'(?:\{[^}]*\})?\s+([0-9.eE+\-]+)(?:\s|$)', re.MULTILINE)
    return sum(float(match.group(1)) for match in pattern.finditer(text))
