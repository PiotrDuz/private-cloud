#!/usr/bin/env python3
"""Verify the media gateway tunnel uses the configured AirVPN peer key, endpoint port, and keepalive."""

import json
import subprocess
import sys
from pathlib import Path


NETNS_DIRECTORY = Path("/run/netns")


def main():
    config = json.load(sys.stdin)
    namespace = gateway_namespace(config["interface"])
    peers = peer_rows(namespace, config["interface"])
    if len(peers) != 1:
        raise RuntimeError(f"The media gateway tunnel has {len(peers)} peers instead of one")
    public_key, endpoint, handshake, keepalive = peers[0]
    if public_key != config["peer_public_key"]:
        raise RuntimeError("The media gateway peer key differs from media.vpn.peer_public_key; update the key or the gluetun server list")
    if int(endpoint.rsplit(":", 1)[1]) != config["endpoint_port"]:
        raise RuntimeError(f"The media gateway connects to {endpoint} instead of port {config['endpoint_port']}")
    if keepalive != str(config["persistent_keepalive"] or "off"):
        raise RuntimeError(f"The media gateway keepalive is {keepalive} instead of {config['persistent_keepalive']}")
    if int(handshake) == 0:
        raise RuntimeError("The media gateway tunnel has not completed a handshake")
    print(json.dumps({"endpoint": endpoint, "peer_public_key": public_key, "result": "passed"}, separators=(",", ":")))


def gateway_namespace(interface):
    names = sorted(path.name for path in NETNS_DIRECTORY.iterdir()) if NETNS_DIRECTORY.is_dir() else []
    matches = [name for name in names if is_kernel_wireguard(name, interface)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one pod network namespace with a kernel WireGuard {interface}, found {len(matches)}")
    return matches[0]


def is_kernel_wireguard(namespace, interface):
    result = subprocess.run(["ip", "-j", "-d", "-n", namespace, "link", "show", "dev", interface], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    return any(link.get("linkinfo", {}).get("info_kind") == "wireguard" for link in json.loads(result.stdout or "[]"))


def peer_rows(namespace, interface):
    dump = subprocess.run(["ip", "netns", "exec", namespace, "wg", "show", interface, "dump"], capture_output=True, text=True, check=True).stdout
    rows = [line.split("\t") for line in dump.splitlines()[1:]]
    return [(row[0], row[2], row[4], row[7]) for row in rows]


if __name__ == "__main__":
    main()
