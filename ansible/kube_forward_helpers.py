"""Helpers shared by scripts that reach services through a kubectl port-forward."""

import select
import socket
import time


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
