"""HTTPS requests and OAuth response inspection for the identity validator."""

import http.client
import json
import socket
import urllib.parse

from public_tls import public_context

WRONG_REDIRECT = "https://private-cloud-validation.invalid/callback"
WRONG_SECRET = "private-cloud-validation-wrong-secret"
PROBE_CODE = "private-cloud-validation-code"


def https_request(address, host, method, path, headers=None, form=None):
    body = urllib.parse.urlencode(form) if form is not None else None
    request_headers = {"Host": host, "User-Agent": "private-cloud-validator", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    with socket.create_connection((address, 443), timeout=20) as raw:
        with public_context().wrap_socket(raw, server_hostname=host) as secured:
            client = http.client.HTTPSConnection(host, 443, timeout=20)
            client.sock = secured
            client.request(method, path, body=body, headers=request_headers)
            response = client.getresponse()
            text = response.read(1024 * 1024).decode(errors="replace")
            return response.status, response, text


def authorize_query(client_id, redirect):
    return urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "openid",
        "state": "private-cloud-validation",
        "nonce": "private-cloud-validation",
        "code_challenge": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "code_challenge_method": "S256",
    })


def redirect_target(base_url, status, response):
    """Return the absolute redirect target, or raise when the response is not a redirect."""
    location = response.getheader("Location")
    if status not in (302, 303, 307) or not location:
        raise RuntimeError(f"expected a redirect, received HTTP {status}")
    return urllib.parse.urlsplit(urllib.parse.urljoin(base_url, location))


def error_parameters(target):
    parameters = urllib.parse.parse_qs(target.query)
    parameters.update(urllib.parse.parse_qs(target.fragment))
    return {name: parameters[name][0] for name in ("error", "error_description") if name in parameters}


def token_error(address, hostname, token_path, client, redirect, secret):
    form = {
        "grant_type": "authorization_code",
        "code": PROBE_CODE,
        "redirect_uri": redirect,
        "client_id": client,
    }
    if secret:
        form["client_secret"] = secret
    status, _, text = https_request(address, hostname, "POST", token_path, form=form)
    try:
        error = json.loads(text).get("error", "")
    except ValueError:
        error = ""
    if status < 400 or not error:
        raise RuntimeError(f"OpenCloud token endpoint answered the {client} probe with HTTP {status} and no OAuth error")
    return error
