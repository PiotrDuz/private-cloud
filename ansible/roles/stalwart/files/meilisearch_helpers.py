"""Meilisearch key management through a temporary Kubernetes port-forward."""
import contextlib
import http.client
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from kube_forward_helpers import find_free_port, wait_for_forward  # noqa: E402


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


def ensure_key(address, master_key, desired):
    existing = request(address, master_key, "GET", f"/keys/{desired['uid']}", allowed=(200, 404))
    if existing["status"] == 200:
        if key_matches(existing["body"], desired):
            return existing["body"]["key"]
        request(address, master_key, "DELETE", f"/keys/{desired['uid']}", allowed=(204,))
    created = request(address, master_key, "POST", "/keys", desired, allowed=(201,))
    return created["body"]["key"]


def key_matches(current, desired):
    return (
        sorted(current["actions"]) == sorted(desired["actions"])
        and sorted(current["indexes"]) == sorted(desired["indexes"])
        and current["expiresAt"] is None
    )


def request(address, token, method, path, payload=None, allowed=(200,)):
    connection = http.client.HTTPConnection(*address, timeout=20)
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    text = response.read().decode()
    connection.close()
    if response.status not in allowed:
        raise RuntimeError(f"Meilisearch {method} {path} returned HTTP {response.status}")
    return {"status": response.status, "body": json.loads(text) if text else None}
