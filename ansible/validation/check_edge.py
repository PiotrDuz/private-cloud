#!/usr/bin/env python3
"""Check installed edge routes, publicly trusted unexpired TLS, and the identity provider discovery document."""

import json
import socket
import sys
import urllib.parse

from http_helpers import https_certificate_days, https_get, smtp_tls


MINIMUM_CERTIFICATE_DAYS = 14


def main():
    config = json.load(sys.stdin)
    address = config["address"]
    results = []
    for site in config["sites"]:
        host = site["host"]
        resolved = sorted({entry[4][0] for entry in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)})
        if resolved != [address]:
            raise RuntimeError(f"Split DNS resolves {host} to {resolved} instead of {address}")
        status, payload = https_get(address, host, site.get("path", "/"))
        if status >= 400 and status not in (401, 403):
            raise RuntimeError(f"{host} returned HTTP {status}")
        if "issuer" in site:
            document = json.loads(payload)
            if document.get("issuer") != site["issuer"]:
                raise RuntimeError(f"{host} advertises an unexpected OIDC issuer")
            jwks_url = urllib.parse.urlsplit(document.get("jwks_uri", ""))
            if jwks_url.hostname != host or jwks_url.scheme != "https":
                raise RuntimeError(f"{host} advertises an invalid OIDC JWKS URL")
            jwks_status, jwks_payload = https_get(address, host, jwks_url.path)
            if jwks_status != 200 or not json.loads(jwks_payload).get("keys"):
                raise RuntimeError(f"{host} did not serve OIDC signing keys")
        days = https_certificate_days(address, host)
        require_fresh(host, days)
        results.append({"host": host, "status": status, "certificate_days": days})
    if config.get("smtp_host"):
        days = smtp_tls(address, config["smtp_host"])
        require_fresh(config["smtp_host"], days)
        results.append({"host": config["smtp_host"], "port": 25, "starttls": True, "certificate_days": days})
    print(json.dumps({"checked": results}, separators=(",", ":")))


def require_fresh(host, days):
    if days < MINIMUM_CERTIFICATE_DAYS:
        raise RuntimeError(f"{host} certificate expires in {days} days; certificate renewal is failing")


if __name__ == "__main__":
    main()
