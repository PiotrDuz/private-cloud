#!/usr/bin/env python3
"""Run a CPU face-detection inference against the configured Immich ML service."""

import http.client
import json
import secrets
import socket
import subprocess
import sys

from application_helpers import find_free_port, wait_for_forward


def main():
    config = json.load(sys.stdin)
    local_port, forward = start_port_forward(config)
    try:
        response = run_inference(config, local_port)
        validate_inference(config, response)
    finally:
        stop_port_forward(forward)
    print(json.dumps({"service": config["service"], "status": "passed", "inference": "cpu-face-detection"}))


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


def run_inference(config, local_port):
    boundary = "private-cloud-" + secrets.token_hex(16)
    entries = json.dumps({
        "facial-recognition": {
            "detection": {
                "modelName": config["model_name"],
                "options": {"minScore": 0.7},
            },
        },
    }, separators=(",", ":"))
    image = blank_ppm(config["image_size"])
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="entries"\r\n\r\n'
        f"{entries}\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="image"; filename="private-cloud-validation.ppm"\r\n'
        "Content-Type: image/x-portable-pixmap\r\n\r\n"
    ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
    connection = http.client.HTTPConnection("127.0.0.1", local_port, timeout=360)
    try:
        connection.request(
            "POST", "/predict", body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        response = connection.getresponse()
        payload = response.read(1024 * 1024 + 1)
        if response.status != 200:
            raise RuntimeError(f"Immich ML inference returned HTTP {response.status}")
        if len(payload) > 1024 * 1024:
            raise RuntimeError("Immich ML inference returned an unexpectedly large response")
        try:
            return json.loads(payload)
        except json.JSONDecodeError as error:
            raise RuntimeError("Immich ML inference returned invalid JSON") from error
    finally:
        connection.close()


def validate_inference(config, response):
    width = config["image_size"]
    task = response.get("facial-recognition")
    if response.get("imageWidth") != width or response.get("imageHeight") != width:
        raise RuntimeError("Immich ML inference returned the wrong image dimensions")
    if not isinstance(task, dict) or not all(isinstance(task.get(key), list) for key in ("boxes", "scores", "landmarks")):
        raise RuntimeError("Immich ML inference did not return face-detection outputs")
    if not (len(task["boxes"]) == len(task["scores"]) == len(task["landmarks"])):
        raise RuntimeError("Immich ML face-detection outputs have inconsistent lengths")


def blank_ppm(size):
    return f"P6\n{size} {size}\n255\n".encode() + bytes((96, 128, 160)) * size * size


def stop_port_forward(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


if __name__ == "__main__":
    main()
