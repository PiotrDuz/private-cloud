#!/usr/bin/env python3
"""Resolve the configured relay to public IPv4 policy destinations."""
import ipaddress
import json
import socket
import sys


def main():
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(sys.argv[1], None, socket.AF_INET, socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("The SMTP relay must resolve to public IPv4 addresses")
    print(json.dumps(addresses))


if __name__ == "__main__":
    main()
