"""Read trusted edge HTTPS and SMTP endpoints through the local Traefik address."""

import http.client
import smtplib
import socket
import ssl


def https_get(address, host, path):
    context = ssl.create_default_context()
    with socket.create_connection((address, 443), timeout=20) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secured:
            client = http.client.HTTPSConnection(host, 443, timeout=20)
            client.sock = secured
            client.request("GET", path, headers={"Host": host, "User-Agent": "private-cloud-validator"})
            response = client.getresponse()
            return response.status, response.read(1024 * 1024).decode(errors="replace")


def smtp_tls(address, host):
    with smtplib.SMTP(timeout=20) as client:
        client.connect(address, 25)
        client._host = host
        client.ehlo()
        if not client.has_extn("starttls"):
            raise RuntimeError(f"{host} did not advertise SMTP STARTTLS")
        client.starttls(context=ssl.create_default_context())
