"""IMAP state, Received header parsing, and Proxy Protocol SMTP delivery for imap_fetch.py."""

import email.parser
import email.utils
import imaplib
import ipaddress
import json
import os
import re
import smtplib
import struct
import sys
import time

STALWART_SMTP = ("127.0.0.1", 25)
FALLBACK_CLIENT = ("[127.0.0.1]", "127.0.0.1")
PROXY_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
RECEIVED = re.compile(r"^from\s+(\S+)\s+\((?:[^()\[\]]*\s)?\[(?:IPv6:)?([0-9A-Fa-f:.]+)\]\)\s+by\s+(\S+)", re.IGNORECASE)


class ProxySMTP(smtplib.SMTP):
    """SMTP client that opens the session with a Proxy Protocol v2 header naming the original client."""

    def __init__(self, address, helo):
        self.proxy_header = proxy_header(ipaddress.ip_address(address))
        super().__init__(*STALWART_SMTP, local_hostname=helo, timeout=60)

    def _get_socket(self, host, port, timeout):
        sock = super()._get_socket(host, port, timeout)
        sock.sendall(self.proxy_header)
        return sock


def edge_client(raw, receiver_domain):
    """Return the HELO and address of the first public client in the provider's own top Received headers."""
    headers = email.parser.BytesHeaderParser().parsebytes(raw)
    for value in headers.get_all("Received") or []:
        match = RECEIVED.match(" ".join(str(value).split()))
        if not match or not is_within(match.group(3).lower().rstrip(";"), receiver_domain):
            break
        try:
            address = ipaddress.ip_address(match.group(2))
        except ValueError:
            break
        if address.is_global:
            return helo_name(match.group(1), address), str(address)
    return FALLBACK_CLIENT


def envelope_sender(raw):
    value = email.parser.BytesHeaderParser().parsebytes(raw).get("Return-Path", "")
    return email.utils.parseaddr(str(value))[1]


def examine(imap):
    status, _ = imap.select("INBOX", readonly=True)
    if status != "OK":
        raise imaplib.IMAP4.error("Cannot open INBOX")
    uidvalidity = int(imap.response("UIDVALIDITY")[1][0])
    status, data = imap.status("INBOX", "(UIDNEXT)")
    uidnext = int(re.search(rb"UIDNEXT (\d+)", data[0]).group(1))
    return uidvalidity, uidnext


def new_uids(imap, last_uid):
    status, data = imap.uid("search", None, f"UID {last_uid + 1}:*")
    if status != "OK":
        raise imaplib.IMAP4.error("Cannot search INBOX")
    return sorted(uid for uid in map(int, data[0].split()) if uid > last_uid)


def read_state(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def write_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as handle:
        json.dump({**state, "checked": int(time.time())}, handle)
    os.replace(path + ".tmp", path)


def log(event, **fields):
    print(json.dumps({"event": event, **fields}), file=sys.stdout, flush=True)


def proxy_header(address):
    if address.version == 4:
        return PROXY_SIGNATURE + b"\x21\x11" + struct.pack("!H", 12) + address.packed + ipaddress.ip_address("127.0.0.1").packed + struct.pack("!HH", 0, 25)
    return PROXY_SIGNATURE + b"\x21\x21" + struct.pack("!H", 36) + address.packed + ipaddress.ip_address("::1").packed + struct.pack("!HH", 0, 25)


def helo_name(helo, address):
    """Clients often greet with a bare hostname; Stalwart requires a domain, so fall back to the address literal."""
    if HOSTNAME.match(helo):
        return helo
    return f"[{address}]" if address.version == 4 else f"[IPv6:{address}]"


def is_within(host, domain):
    return host == domain or host.endswith("." + domain)
