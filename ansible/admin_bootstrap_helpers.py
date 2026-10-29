"""Helpers for scripts that claim an unclaimed application through a temporary port-forward."""

import contextlib
import http.client
import json
import subprocess

from kube_forward_helpers import find_free_port, wait_for_forward


@contextlib.contextmanager
def port_forward(kubeconfig, namespace, service, port):
    local_port = find_free_port()
    process = subprocess.Popen(
        [
            "k0s", "kubectl", "--kubeconfig", kubeconfig, "--namespace", namespace,
            "port-forward", "--address", "127.0.0.1", f"service/{service}", f"{local_port}:{port}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        wait_for_forward(process, local_port)
        yield ("127.0.0.1", local_port)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def request_json(address, method, path, payload=None, allowed=(200,), name="application", headers=None):
    connection = http.client.HTTPConnection(*address, timeout=30)
    headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        text = response.read().decode(errors="replace")
    finally:
        connection.close()
    if response.status not in allowed:
        raise RuntimeError(f"{name} {method} {path} returned HTTP {response.status}")
    return json.loads(text) if text else None


def opencloud_app_token(kubeconfig, namespace, target, username, expiration):
    """The OpenCloud auth-app service issues short-lived tokens that work as Basic auth passwords."""
    command = [
        "k0s", "kubectl", "--kubeconfig", kubeconfig, "--namespace", namespace, "exec", target, "-c", "opencloud", "--",
        "opencloud", "auth-app", "create", "--user-name=" + username, "--expiration=" + expiration,
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError("OpenCloud could not create an app token for " + username)
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        key, separator, value = line.strip().partition(":")
        if separator and key.strip().casefold() == "token" and value.strip():
            return value.strip()
    raise RuntimeError("OpenCloud app token creation returned no token")
