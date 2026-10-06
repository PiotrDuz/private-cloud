#!/usr/bin/env python3
"""Run local service mocks for a disposable live installation."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from mock_helpers import (
    ARTIFACTS, allow_acme, allow_cloudflare, enable_stalwart_relay, install_cluster_dns,
    install_cluster_trust, install_host_trust, install_traefik_certificate,
    prepare, read_configuration, run_ddns, serve_smtp, start_acme, start_cloudflare,
    start_openvpn, start_smtp, stop_openvpn, stop_service, stop_smtp,
    restore_mocks,
)
from stalwart_certificate import issue_stalwart_certificate
from vpn_fixtures import validate_amneziawg_peer, validate_killswitch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=[
        "prepare", "restore", "install-host-trust", "install-cluster-dns", "install-cluster-trust", "install-traefik-cert",
        "enable-stalwart-relay", "start-openvpn", "stop-openvpn", "start-smtp", "stop-smtp", "smtp-server",
        "start-cloudflare", "stop-cloudflare", "allow-cloudflare", "run-ddns", "start-acme", "stop-acme", "allow-acme",
        "issue-stalwart-certificate",
        "validate-vpn-killswitch", "validate-amneziawg-peer",
    ])
    parser.add_argument("--config", type=Path, default=Path("/tank/secure/backup/private-cloud-config/private-cloud.yml"))
    arguments = parser.parse_args()
    ARTIFACTS.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.geteuid() != 0:
        raise RuntimeError("The live mock harness must run as root")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    boot_file = ARTIFACTS / "boot-id"
    if not boot_file.exists() or boot_file.read_text().strip() != boot_id:
        for pid_file in ARTIFACTS.glob("*.pid"):
            pid_file.unlink()
        boot_file.write_text(boot_id + "\n")
    configuration = read_configuration(arguments.config)
    if arguments.action == "prepare":
        prepare(configuration)
    elif arguments.action == "restore":
        restore_mocks(configuration, arguments.config)
    elif arguments.action == "start-openvpn":
        start_openvpn(configuration)
    elif arguments.action == "stop-openvpn":
        stop_openvpn()
    elif arguments.action == "install-host-trust":
        install_host_trust()
    elif arguments.action == "install-cluster-dns":
        install_cluster_dns(configuration)
    elif arguments.action == "install-cluster-trust":
        install_cluster_trust()
    elif arguments.action == "install-traefik-cert":
        install_traefik_certificate()
    elif arguments.action == "enable-stalwart-relay":
        enable_stalwart_relay(configuration)
    elif arguments.action == "start-smtp":
        start_smtp(configuration)
    elif arguments.action == "stop-smtp":
        stop_smtp()
    elif arguments.action == "smtp-server":
        asyncio.run(serve_smtp(configuration))
    elif arguments.action == "allow-acme":
        allow_acme(configuration)
    elif arguments.action == "start-acme":
        start_acme(configuration, arguments.config)
    elif arguments.action == "stop-acme":
        stop_service("acme-mock.pid")
    elif arguments.action == "start-cloudflare":
        start_cloudflare(configuration, arguments.config)
    elif arguments.action == "stop-cloudflare":
        stop_service("cloudflare-mock.pid")
    elif arguments.action == "allow-cloudflare":
        allow_cloudflare(configuration)
    elif arguments.action == "run-ddns":
        run_ddns(configuration)
    elif arguments.action == "issue-stalwart-certificate":
        print(json.dumps(issue_stalwart_certificate(configuration), separators=(",", ":")))
    elif arguments.action == "validate-vpn-killswitch":
        validate_killswitch(configuration)
    elif arguments.action == "validate-amneziawg-peer":
        validate_amneziawg_peer(configuration)



if __name__ == "__main__":
    main()
