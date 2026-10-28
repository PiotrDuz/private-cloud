#!/usr/bin/env python3
"""Request a fresh Stalwart ACME renewal when the TLS hostname has no certificate and wait for issuance."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from admin_bootstrap_helpers import port_forward  # noqa: E402
from jmap_helpers import certificate_hostnames, create_acme_renewal, domain_id  # noqa: E402


def main():
    config = json.load(sys.stdin)
    credentials = {"username": config["username"], "password": config["password"]}
    with port_forward(config["kubeconfig"], config["namespace"], config["service"], config["port"]) as address:
        if config["hostname"] in certificate_hostnames(address, credentials):
            print(json.dumps({"changed": False}))
            return
        create_acme_renewal(address, credentials, domain_id(address, credentials, config["hostname"]))
        wait_for_certificate(address, credentials, config["hostname"], config["timeout"])
    print(json.dumps({"changed": True}))


def wait_for_certificate(address, credentials, hostname, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if hostname in certificate_hostnames(address, credentials):
            return
        time.sleep(10)
    raise TimeoutError(f"Stalwart did not obtain a certificate for {hostname} within {timeout} seconds")


if __name__ == "__main__":
    main()
