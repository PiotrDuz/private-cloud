#!/usr/bin/env python3
"""Resolve the configured relay to public or configured local IPv4 policy destinations."""
import ipaddress
import json
import socket
import sys


def main():
    networks = [ipaddress.ip_network(cidr) for cidr in sys.argv[2:]]
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(sys.argv[1], None, socket.AF_INET, socket.SOCK_STREAM)})
    if not addresses or not all(allowed(address, networks) for address in addresses):
        raise ValueError("The SMTP relay must resolve to public or configured local IPv4 addresses")
    print(json.dumps(addresses))


def allowed(address, networks):
    address = ipaddress.ip_address(address)
    return address.is_global or any(address in network for network in networks)


if __name__ == "__main__":
    main()
