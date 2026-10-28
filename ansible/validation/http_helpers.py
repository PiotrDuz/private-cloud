"""Read publicly trusted edge HTTPS endpoints through the local Traefik address."""

import http.client
import socket
import ssl
import time

from public_tls import public_context


def https_get(address, host, path):
    context = public_context()
    with socket.create_connection((address, 443), timeout=20) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secured:
            client = http.client.HTTPSConnection(host, 443, timeout=20)
            client.sock = secured
            client.request("GET", path, headers={"Host": host, "User-Agent": "private-cloud-validator"})
            response = client.getresponse()
            return response.status, response.read(1024 * 1024).decode(errors="replace")


def https_certificate_days(address, host):
    with socket.create_connection((address, 443), timeout=20) as raw:
        with public_context().wrap_socket(raw, server_hostname=host) as secured:
            return remaining_days(secured.getpeercert())


def remaining_days(certificate):
    return int((ssl.cert_time_to_seconds(certificate["notAfter"]) - time.time()) // 86400)
