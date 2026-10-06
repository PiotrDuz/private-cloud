"""Helpers shared by the private-cloud application validators."""

import http.client
import json
import select
import socket
import subprocess
import time


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


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_forward(process, local_port):
    deadline = time.monotonic() + 30
    output_lines = []
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output_lines.append(process.stdout.read() if process.stdout else "")
            raise RuntimeError(f"kubectl port-forward exited early: {''.join(output_lines).strip()}")
        ready, _, _ = select.select([process.stdout], [], [], 0.25)
        if ready:
            output = process.stdout.readline()
            output_lines.append(output)
            if "Forwarding from 127.0.0.1:" in output:
                with socket.create_connection(("127.0.0.1", local_port), timeout=2):
                    return
            if output:
                continue
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.25):
                return
        except OSError:
            pass
    raise TimeoutError("kubectl port-forward did not become ready")


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
