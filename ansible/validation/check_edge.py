#!/usr/bin/env python3
"""Check installed edge routes, trusted TLS, and the realm discovery document."""

import json
import socket
import sys
import urllib.parse

from http_helpers import https_get, smtp_tls


def main():
    config = json.load(sys.stdin)
    address = config["address"]
    results = []
    for site in config["sites"]:
        host = site["host"]
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
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
        results.append({"host": host, "status": status})
    if config.get("smtp_host"):
        smtp_tls(address, config["smtp_host"])
        results.append({"host": config["smtp_host"], "port": 25, "starttls": True})
    print(json.dumps({"checked": results}, separators=(",", ":")))


if __name__ == "__main__":
    main()
