#!/usr/bin/env python3
"""Check public DNS and mail authentication records through independent public resolvers."""

import ipaddress
import json
import sys
import urllib.request

from dns_helpers import resolve, reverse_name
from public_tls import public_context


RESOLVERS = ("1.1.1.1", "8.8.8.8")


def main():
    config = json.load(sys.stdin)
    address = public_address(config["public_ip_url"])
    for resolver in RESOLVERS:
        for name in config["records"]:
            require_address(resolver, name, address)
        if config.get("mail"):
            require_mail_records(resolver, config["mail"], address)
    print(json.dumps({"public_address": address, "resolvers": RESOLVERS, "records": len(config["records"])}, separators=(",", ":")))


def require_mail_records(resolver, mail, address):
    exchangers = resolve(resolver, mail["forwarding_domain"], "MX")
    if mail["hostname"] not in exchangers:
        raise RuntimeError(f"{resolver}: MX for {mail['forwarding_domain']} does not include {mail['hostname']}")
    primary = resolve(resolver, mail["domain"], "MX")
    if not primary or mail["hostname"] in primary:
        raise RuntimeError(f"{resolver}: MX for {mail['domain']} must point at the external inbox provider")
    if not any(record.lower().startswith("v=spf1 ") for record in resolve(resolver, mail["domain"], "TXT")):
        raise RuntimeError(f"{resolver}: {mail['domain']} has no SPF record")
    if not any(record.upper().startswith("V=DMARC1") for record in resolve(resolver, "_dmarc." + mail["domain"], "TXT")):
        raise RuntimeError(f"{resolver}: {mail['domain']} has no DMARC record")
    if resolve(resolver, reverse_name(address), "PTR") != [mail["hostname"]]:
        raise RuntimeError(f"{resolver}: PTR for {address} is not {mail['hostname']}")


def require_address(resolver, name, address):
    answers = resolve(resolver, name, "A")
    if answers != [address]:
        raise RuntimeError(f"{resolver}: {name} resolves to {answers or 'nothing'} instead of {address}")


def public_address(url):
    with urllib.request.urlopen(url, timeout=15, context=public_context()) as response:
        value = ipaddress.IPv4Address(response.read(64).decode().strip())
    if not value.is_global:
        raise RuntimeError(f"{url} returned non-public address {value}")
    return str(value)


if __name__ == "__main__":
    main()
