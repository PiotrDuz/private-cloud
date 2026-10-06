"""Wait for a TCP service endpoint before starting dependent work."""

import socket
import sys
import time


def main():
    endpoint = (sys.argv[1], int(sys.argv[2]))
    timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    deadline = time.monotonic() + timeout if timeout > 0 else None
    while deadline is None or time.monotonic() < deadline:
        try:
            with socket.create_connection(endpoint, timeout=2):
                return 0
        except OSError:
            time.sleep(1)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
