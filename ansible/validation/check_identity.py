#!/usr/bin/env python3
"""Verify the Stalwart OIDC provider, its registered application clients, and the Grist ForwardAuth login redirect."""

import json
import sys
import urllib.parse

from identity_helpers import https_request, oauth_clients, redirect_target


def main():
    config = json.load(sys.stdin)
    discovery = read_discovery(config)
    check_signing_keys(config, discovery)
    check_clients(config)
    if config.get("forward_auth"):
        check_forward_auth(config, discovery)
    print(json.dumps({"clients": sorted(client["id"] for client in config["clients"])}, separators=(",", ":")))


def read_discovery(config):
    status, _, body = https_request(config["address"], config["hostname"], "GET", "/.well-known/openid-configuration")
    if status != 200:
        raise RuntimeError(f"Stalwart discovery returned HTTP {status}")
    discovery = json.loads(body)
    if discovery["issuer"] != "https://" + config["hostname"]:
        raise RuntimeError("Stalwart discovery does not match the configured HTTPS issuer")
    for name in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri"):
        endpoint = urllib.parse.urlsplit(discovery[name])
        if endpoint.scheme != "https" or endpoint.netloc != config["hostname"]:
            raise RuntimeError(f"Stalwart discovery {name} does not match the configured HTTPS issuer")
    return discovery


def check_signing_keys(config, discovery):
    """Applications verify ID tokens against public ES256 keys, which an HMAC algorithm would not publish."""
    path = urllib.parse.urlsplit(discovery["jwks_uri"]).path
    status, _, body = https_request(config["address"], config["hostname"], "GET", path)
    if status != 200 or not any(key.get("alg") == "ES256" for key in json.loads(body).get("keys", [])):
        raise RuntimeError("Stalwart does not publish an ES256 ID token signing key")


def check_clients(config):
    registered = oauth_clients(config["address"], config["hostname"], config["username"], config["password"])
    for client in config["clients"]:
        missing = set(client["redirects"]) - registered.get(client["id"], set())
        if client["id"] not in registered or missing:
            raise RuntimeError(f"Stalwart is missing the {client['id']} client or its redirects {sorted(missing)}")


def check_forward_auth(config, discovery):
    """Unauthenticated Grist requests, even with forged identity headers, must be sent to Stalwart sign-in."""
    forward = config["forward_auth"]
    forged = {"X-Forwarded-User": "forged@invalid.invalid", "X-Auth-Request-Email": "forged@invalid.invalid"}
    authorize = urllib.parse.urlsplit(discovery["authorization_endpoint"])
    for path, headers in (("/", forged), ("/oauth2/start?rd=/", {})):
        status, response, _ = https_request(config["address"], forward["hostname"], "GET", path, headers)
        target = redirect_target("https://" + forward["hostname"] + path, status, response)
        query = urllib.parse.parse_qs(target.query)
        if (
            target.netloc != config["hostname"] or target.path != authorize.path
            or query.get("client_id") != [forward["client_id"]]
            or query.get("redirect_uri") != [forward["redirect"]]
            or not any("Secure" in cookie and "HttpOnly" in cookie for cookie in response.headers.get_all("Set-Cookie") or [])
        ):
            raise RuntimeError(f"Grist {path} does not start a secure Stalwart login for {forward['client_id']}")


if __name__ == "__main__":
    main()
