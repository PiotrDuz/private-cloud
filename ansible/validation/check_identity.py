#!/usr/bin/env python3
"""Verify enabled Keycloak clients accept their configured login callbacks."""

import json
import sys
import urllib.parse

from http_helpers import https_get


def main():
    config = json.load(sys.stdin)
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
            "/realms/private-cloud/protocol/openid-connect/auth?" + query,
        )
        if status not in (200, 302, 303):
            raise RuntimeError(f"Keycloak rejected the {client['id']} login callback with HTTP {status}")
        accepted.append(client["id"])
    print(json.dumps({"accepted_clients": accepted}, separators=(",", ":")))


if __name__ == "__main__":
    main()
