"""Read publicly trusted edge HTTPS and SMTP endpoints through the local Traefik address."""

import http.client
import smtplib
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


def smtp_tls(address, host):
    with smtplib.SMTP(timeout=20) as client:
        client.connect(address, 25)
        client._host = host
        client.ehlo()
        if not client.has_extn("starttls"):
            raise RuntimeError(f"{host} did not advertise SMTP STARTTLS")
        client.starttls(context=public_context())
        return remaining_days(client.sock.getpeercert())


def remaining_days(certificate):
    return int((ssl.cert_time_to_seconds(certificate["notAfter"]) - time.time()) // 86400)
