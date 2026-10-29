"""HTTPS requests and redirect inspection for the identity validator."""

import base64
import http.client
import json
import socket
import urllib.parse

from public_tls import public_context

JMAP_USING = ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"]


def https_request(address, host, method, path, headers=None, body=None):
    request_headers = {"Host": host, "User-Agent": "private-cloud-validator", **(headers or {})}
    with socket.create_connection((address, 443), timeout=20) as raw:
        with public_context().wrap_socket(raw, server_hostname=host) as secured:
            client = http.client.HTTPSConnection(host, 443, timeout=20)
            client.sock = secured
            client.request(method, path, body=body, headers=request_headers)
            response = client.getresponse()
            text = response.read(1024 * 1024).decode(errors="replace")
            return response.status, response, text


def redirect_target(base_url, status, response):
    """Return the absolute redirect target, or raise when the response is not a redirect."""
    location = response.getheader("Location")
    if status not in (302, 303, 307) or not location:
        raise RuntimeError(f"expected a redirect, received HTTP {status}")
    return urllib.parse.urlsplit(urllib.parse.urljoin(base_url, location))


def oauth_clients(address, host, username, password):
    """Read the registered OAuth clients through the Stalwart management API."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    body = json.dumps({"using": JMAP_USING, "methodCalls": [
        ["x:OAuthClient/query", {}, "0"],
        ["x:OAuthClient/get", {
            "#ids": {"resultOf": "0", "name": "x:OAuthClient/query", "path": "/ids"},
            "properties": ["clientId", "redirectUris"],
        }, "1"],
    ]})
    status, _, text = https_request(address, host, "POST", "/jmap", {"Authorization": "Basic " + token, "Content-Type": "application/json"}, body)
    if status != 200:
        raise RuntimeError(f"Stalwart management API returned HTTP {status}")
    responses = json.loads(text)["methodResponses"]
    if any(name == "error" for name, _, _ in responses):
        raise RuntimeError("Stalwart management API rejected the OAuth client query")
    return {client["clientId"]: set(client["redirectUris"]) for client in responses[1][1]["list"]}
