#!/usr/bin/env python3
"""Verify OpenCloud admin authentication and persistent WebDAV storage."""

import base64
import http.client
import json
import subprocess
import sys
import uuid

from application_helpers import find_free_port, wait_for_forward


def main():
    config = json.load(sys.stdin)
    pod = ready_pod(config)
    token = create_admin_token(config, pod)
    local_port, forward = start_port_forward(config)
    try:
        verify_storage(config, local_port, token)
    finally:
        stop_port_forward(forward)
    print(json.dumps({"service": config["service"], "status": "passed", "storage": "crud"}))


def ready_pod(config):
    command = [
        "k0s", "kubectl", "--kubeconfig", config["kubeconfig"],
        "--namespace", config["namespace"], "get", "pods",
        "-l", "app.kubernetes.io/name=" + config["service"], "-o", "json",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("OpenCloud pod discovery failed")
    try:
        items = json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenCloud pod discovery returned invalid JSON") from error
    for pod in items:
        metadata = pod.get("metadata", {})
        statuses = pod.get("status", {}).get("containerStatuses", [])
        if (not metadata.get("deletionTimestamp") and
                pod.get("status", {}).get("phase") == "Running" and
                any(item.get("name") == "opencloud" and item.get("ready") for item in statuses)):
            return metadata["name"]
    raise RuntimeError("OpenCloud has no non-terminating Ready pod")


def create_admin_token(config, pod):
    command = [
        "k0s", "kubectl", "--kubeconfig", config["kubeconfig"],
        "--namespace", config["namespace"], "exec", pod, "-c", "opencloud", "--",
        "opencloud", "auth-app", "create",
        "--user-name=" + config["admin_username"], "--expiration=5m",
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError("OpenCloud could not create an app token for its configured administrator")
    for line in (result.stdout + "\n" + result.stderr).splitlines():
        key, separator, value = line.strip().partition(":")
        if separator and key.strip().casefold() == "token" and value.strip():
            return value.strip()
    raise RuntimeError("OpenCloud administrator token creation returned no token")


def start_port_forward(config):
    local_port = find_free_port()
    command = [
        "k0s", "kubectl", "--kubeconfig", config["kubeconfig"],
        "--namespace", config["namespace"], "port-forward", "--address", "127.0.0.1",
        "service/" + config["service"],
        f"{local_port}:{config['remote_port']}",
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    try:
        wait_for_forward(process, local_port)
    except Exception:
        stop_port_forward(process)
        raise
    return local_port, process


def verify_storage(config, local_port, token):
    username = config["admin_username"]
    authorization = "Basic " + base64.b64encode(f"{username}:{token}".encode()).decode()
    path = "/remote.php/webdav/private-cloud-validation-" + str(uuid.uuid4()) + ".txt"
    payload = ("private-cloud-validation-" + str(uuid.uuid4())).encode()
    created = False
    try:
        status, _ = request(local_port, "PUT", path, authorization, payload)
        created = status in (200, 201, 204)
        if not created:
            raise RuntimeError(f"OpenCloud WebDAV create returned HTTP {status}")
        status, content = request(local_port, "GET", path, authorization)
        if status != 200 or content != payload:
            raise RuntimeError(f"OpenCloud WebDAV read-back failed with HTTP {status}")
    finally:
        if created:
            status, _ = request(local_port, "DELETE", path, authorization)
            if status not in (200, 204):
                raise RuntimeError(f"OpenCloud WebDAV cleanup returned HTTP {status}")


def request(local_port, method, path, authorization, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", local_port, timeout=20)
    try:
        connection.request(
            method, path, body=body,
            headers={"Authorization": authorization, "Content-Type": "text/plain"},
        )
        response = connection.getresponse()
        return response.status, response.read(1024 * 1024 + 1)
    finally:
        connection.close()


def stop_port_forward(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


if __name__ == "__main__":
    main()
