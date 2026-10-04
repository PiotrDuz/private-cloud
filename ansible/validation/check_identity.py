#!/usr/bin/env python3
"""Verify enabled OpenCloud clients accept their configured login callbacks."""

import json
import sys
import urllib.parse

from http_helpers import https_get


def main():
    config = json.load(sys.stdin)
    status, body = https_get(config["address"], config["hostname"], "/.well-known/openid-configuration")
    if status != 200:
        raise RuntimeError(f"OpenCloud discovery returned HTTP {status}")
    discovery = json.loads(body)
    issuer = "https://" + config["hostname"]
    endpoint = urllib.parse.urlsplit(discovery["authorization_endpoint"])
    if discovery["issuer"] != issuer or endpoint.scheme != "https" or endpoint.netloc != config["hostname"]:
        raise RuntimeError("OpenCloud discovery does not match the configured HTTPS issuer")
    config["authorization_path"] = endpoint.path
    accepted = []
    for client in config["clients"]:
        query = urllib.parse.urlencode({
            "client_id": client["id"],
            "redirect_uri": client["redirect"],
            "response_type": "code",
            "scope": "openid",
            "state": "private-cloud-validation",
            "nonce": "private-cloud-validation",
            "code_challenge": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "code_challenge_method": "S256",
        })
        status, _ = https_get(
            config["address"], config["hostname"],
            config["authorization_path"] + "?" + query,
        )
        if status not in (200, 302, 303):
            raise RuntimeError(f"OpenCloud rejected the {client['id']} login callback with HTTP {status}")
        accepted.append(client["id"])
    print(json.dumps({"accepted_clients": accepted}, separators=(",", ":")))


if __name__ == "__main__":
    main()
