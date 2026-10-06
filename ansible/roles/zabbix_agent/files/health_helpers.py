"""Bounded Alloy and TLS probes."""
import concurrent.futures
import re
import smtplib
import socket
import ssl
import time
import urllib.request


def collect_alloy(configuration):
    endpoint = configuration["endpoints"]["alloy"]
    paths = {
        "alloy_up": endpoint + "/-/healthy",
        "alloy_metrics": endpoint + "/metrics",
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        requests = {name: executor.submit(read_url, url) for name, url in paths.items()}
        data = {name: future.result() for name, future in requests.items()}
    result = {"alloy_up": int(data["alloy_up"] is not None)}
    result["metrics_up"] = int(data["alloy_metrics"] is not None)
    for key, metric in (
        ("alloy_retries", "loki_write_batch_retries_total"),
        ("alloy_dropped", "loki_write_dropped_entries_total"),
    ):
        result[key] = sum_metric(data["alloy_metrics"] or "", metric)
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
            if response.status < 200 or response.status >= 300:
                return None
            return response.read(8 * 1024 * 1024).decode()
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def sum_metric(text, name):
    pattern = re.compile(r"^" + re.escape(name) + r'(?:\{[^}]*\})?\s+([0-9.eE+\-]+)(?:\s|$)', re.MULTILINE)
    return sum(float(match.group(1)) for match in pattern.finditer(text))
