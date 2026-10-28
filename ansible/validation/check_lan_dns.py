#!/usr/bin/env python3
"""Check LAN split DNS, cluster split DNS, and the encrypted DNS canaries served by the LAN resolver."""

import json
import sys

from dns_helpers import NXDOMAIN, query, resolve


def main():
    config = json.load(sys.stdin)
    lan, cluster = config["lan_address"], config["cluster_dns_ip"]
    for name in config["lan_names"]:
        require_answer(lan, name, [lan])
    for name in config["cluster_names"]:
        require_answer(cluster, name, [config["traefik_cluster_ip"]])
    for name in config["canaries"]:
        rcode, _ = query(lan, name, "A")
        if rcode != NXDOMAIN:
            raise RuntimeError(f"{lan}: encrypted DNS canary {name} returned rcode {rcode} instead of NXDOMAIN")
    for resolver in (lan, cluster):
        if not resolve(resolver, config["public_name"], "A"):
            raise RuntimeError(f"{resolver}: public name {config['public_name']} did not resolve")
    print(json.dumps({"lan_names": len(config["lan_names"]), "cluster_names": len(config["cluster_names"]), "canaries": len(config["canaries"])}, separators=(",", ":")))


def require_answer(resolver, name, expected):
    answers = resolve(resolver, name, "A")
    if answers != expected:
        raise RuntimeError(f"{resolver}: {name} resolves to {answers or 'nothing'} instead of {expected[0]}")


if __name__ == "__main__":
    main()
