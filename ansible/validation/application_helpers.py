"""Helpers shared by the private-cloud application validators."""

import http.client
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kube_forward_helpers import find_free_port, wait_for_forward  # noqa: E402


def validate_http_application(config):
    local_port = find_free_port()
    command = [
        "k0s", "kubectl", "--kubeconfig", config["kubeconfig"],
        "--namespace", config["namespace"], "port-forward",
        "--address", "127.0.0.1", f"service/{config['service']}",
        f"{local_port}:{config['remote_port']}",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        wait_for_forward(process, local_port)
        connection = http.client.HTTPConnection("127.0.0.1", local_port, timeout=20)
        connection.request(
            config.get("method", "GET"),
            config["path"],
            body=config.get("body"),
            headers=config.get("headers", {}),
        )
        response = connection.getresponse()
        payload = response.read(1024 * 1024 + 1)
        connection.close()
        require_response(config, response.status, payload)
        return {"service": config["service"], "status": response.status}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def require_response(config, status, payload):
    allowed = config.get("status_codes", [200])
    if status not in allowed:
        raise RuntimeError(f"{config['service']} returned HTTP {status}; expected {allowed}")
    if len(payload) > 1024 * 1024:
        raise RuntimeError(f"{config['service']} returned an unexpectedly large validation response")
    body = payload.decode(errors="replace")
    expected_text = config.get("body_contains")
    if expected_text is not None and expected_text not in body:
        raise RuntimeError(f"{config['service']} response did not contain its expected validation marker")
    expected_json = config.get("json_equal", {})
    expected_json_keys = config.get("json_keys", [])
    if expected_json or expected_json_keys:
        try:
            document = json.loads(body)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"{config['service']} did not return valid JSON") from error
        for key in expected_json_keys:
            if key not in document:
                raise RuntimeError(f"{config['service']} response is missing {key}")
        for key, expected in expected_json.items():
            if document.get(key) != expected:
                raise RuntimeError(f"{config['service']} returned an unexpected {key} value")
