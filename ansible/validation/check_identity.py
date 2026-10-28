#!/usr/bin/env python3
"""Verify OpenCloud client registrations and the Grist ForwardAuth login redirect."""

import json
import sys
import urllib.parse

from identity_helpers import (
    WRONG_REDIRECT, WRONG_SECRET, authorize_query, error_parameters,
    https_request, redirect_target, token_error,
)

# OpenCloud's identity provider answers client authentication failures with access_denied.
CLIENT_REJECTIONS = {"invalid_client", "access_denied"}


def main():
    config = json.load(sys.stdin)
    discovery = read_discovery(config)
    check_end_session(config, discovery)
    check_sign_in_redirect(config, discovery, config["clients"][0])
    accepted = [check_client(config, discovery, client) for client in config["clients"]]
    if config.get("forward_auth"):
        check_forward_auth(config, discovery)
    print(json.dumps({"accepted_clients": accepted}, separators=(",", ":")))


def read_discovery(config):
    status, _, body = https_request(config["address"], config["hostname"], "GET", "/.well-known/openid-configuration")
    if status != 200:
        raise RuntimeError(f"OpenCloud discovery returned HTTP {status}")
    discovery = json.loads(body)
    issuer = "https://" + config["hostname"]
    for name in ("authorization_endpoint", "token_endpoint"):
        endpoint = urllib.parse.urlsplit(discovery[name])
        if endpoint.scheme != "https" or endpoint.netloc != config["hostname"]:
            raise RuntimeError(f"OpenCloud discovery {name} does not match the configured HTTPS issuer")
    if discovery["issuer"] != issuer:
        raise RuntimeError("OpenCloud discovery does not match the configured HTTPS issuer")
    return discovery


def check_end_session(config, discovery):
    expected = "https://" + config["hostname"] + config.get("end_session_path", "")
    if config.get("end_session_path") and discovery.get("end_session_endpoint") != expected:
        raise RuntimeError(f"OpenCloud end_session_endpoint is not {expected}")


def check_sign_in_redirect(config, discovery, client):
    """An unauthenticated authorize request must redirect to the OpenCloud sign-in page without an OAuth error."""
    path = urllib.parse.urlsplit(discovery["authorization_endpoint"]).path
    status, response, _ = https_request(
        config["address"], config["hostname"], "GET", path + "?" + authorize_query(client["id"], client["redirect"]),
    )
    target = redirect_target(discovery["authorization_endpoint"], status, response)
    errors = error_parameters(target)
    callback = target._replace(query="", fragment="").geturl() == client["redirect"]
    if errors or target.netloc != config["hostname"] or callback:
        raise RuntimeError(f"OpenCloud did not redirect the {client['id']} login to its sign-in page: {errors or target.geturl()[:80]}")


def check_client(config, discovery, client):
    """The token endpoint authenticates the client and redirect before it looks at the code."""
    path = urllib.parse.urlsplit(discovery["token_endpoint"]).path
    probe = lambda redirect, secret: token_error(config["address"], config["hostname"], path, client["id"], redirect, secret)
    if probe(client["redirect"], client.get("secret")) != "invalid_grant":
        raise RuntimeError(f"OpenCloud rejected the {client['id']} client or its {client['redirect']} redirect")
    if probe(WRONG_REDIRECT, client.get("secret")) not in CLIENT_REJECTIONS:
        raise RuntimeError(f"OpenCloud accepted an unregistered redirect for {client['id']}")
    if client.get("secret") and probe(client["redirect"], WRONG_SECRET) not in CLIENT_REJECTIONS:
        raise RuntimeError(f"OpenCloud accepted a wrong secret for {client['id']}")
    return client["id"]


def check_forward_auth(config, discovery):
    """Unauthenticated Grist requests, even with forged identity headers, must be sent to OpenCloud sign-in."""
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
            raise RuntimeError(f"Grist {path} does not start a secure OpenCloud login for {forward['client_id']}")


if __name__ == "__main__":
    main()
