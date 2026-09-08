"""Bounded HTTP and TLS probes without application credentials."""
import concurrent.futures
import json
import re
import smtplib
import socket
import ssl
import time
import urllib.parse
import urllib.request


def collect_pipeline(endpoints):
    paths = {"loki_up": endpoints["loki"] + "/ready", "alloy_up": endpoints["alloy"] + "/-/healthy", "grafana_up": endpoints["grafana"] + "/api/health"}
    query = 'sum(count_over_time({job="host",service="private-cloud-log-heartbeat.service"}[5m])) or vector(0)'
    paths["heartbeat"] = endpoints["loki"] + "/loki/api/v1/query?" + urllib.parse.urlencode({"query": query})
    paths.update({name + "_metrics": url + "/metrics" for name, url in endpoints.items()})
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        requests = {name: executor.submit(read_url, url) for name, url in paths.items()}
        data = {name: future.result() for name, future in requests.items()}
    result = {name: int(data[name] is not None) for name in ("loki_up", "alloy_up", "grafana_up")}
    result["heartbeat"] = 0
    try:
        result["heartbeat"] = int(float(json.loads(data["heartbeat"])["data"]["result"][0]["value"][1]) > 0)
    except (ValueError, TypeError, KeyError, IndexError):
        pass
    result["metrics_up"] = int(all(data[name + "_metrics"] is not None for name in endpoints))
    for key, source, metric in (
        ("alloy_retries", "alloy", "loki_write_batch_retries_total"),
        ("alloy_dropped", "alloy", "loki_write_dropped_entries_total"),
        ("loki_discarded", "loki", "loki_discarded_samples_total"),
        ("grafana_notifications_failed", "grafana", "alertmanager_notifications_failed_total"),
    ):
        result[key] = sum_metric(data[source + "_metrics"] or "", metric)
    return result


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


def read_url(url):
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "private-cloud-health"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.read(8 * 1024 * 1024).decode()
    except (OSError, ValueError):
        return None


def sum_metric(text, name):
    pattern = re.compile(r"^" + re.escape(name) + r'(?:\{[^}]*\})?\s+([0-9.eE+\-]+)(?:\s|$)', re.MULTILINE)
    return sum(float(match.group(1)) for match in pattern.finditer(text))
