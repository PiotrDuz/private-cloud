#!/usr/bin/env python3
"""Serve the Cloudflare API subset and address lookup used by live validation."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import ssl
import sys
from urllib.parse import parse_qs, urlsplit

import yaml


ARTIFACTS = Path("/var/lib/private-cloud-live-test")
RECORDS = ARTIFACTS / "cloudflare-records.json"


def main():
    configuration = read_configuration(Path(sys.argv[1]))
    cloud = configuration["private_cloud"]
    network = cloud["networking"]
    endpoint = urlsplit(network.get("cloudflare_api_url", "https://api.cloudflare.com/client/v4"))
    if endpoint.scheme != "https" or not endpoint.hostname or not endpoint.port:
        raise ValueError("The live test Cloudflare API URL must be HTTPS with an explicit port")
    allowed_records = set(network["managed_records"])
    allowed_records.update([network["zabbix_hostname"], network["amneziawg"]["hostname"]])
    allowed_records.update(cloud[stage]["hostname"] for stage in ("media", "onlyoffice", "opencloud", "grist", "affine", "immich", "stalwart", "logging"))
    api_prefix = endpoint.path.rstrip("/")
    ensure_records()
    handler = make_handler(api_prefix, network["cloudflare_zone_id"], allowed_records, network["traefik_internal_ip"])
    server = ThreadingHTTPServer(("0.0.0.0", endpoint.port), handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(ARTIFACTS / "server.crt"), str(ARTIFACTS / "server.key"))
    # Handshake in each handler thread so one stalled client cannot block accept().
    server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    server.serve_forever()


def make_handler(api_prefix, zone_id, allowed_records, public_address):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PrivateCloudCloudflareMock/1"
        timeout = 10

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/ip":
                self.send_text(str(ipaddress.IPv4Address(public_address)) + "\n")
                return
            if not self.authorized():
                return
            prefix = f"{api_prefix}/zones/{zone_id}/dns_records"
            if parsed.path == prefix:
                name = parse_qs(parsed.query).get("name", [""])[0]
                record_type = parse_qs(parsed.query).get("type", [""])[0]
                if record_type != "A" or name not in allowed_records:
                    self.send_json({"success": False, "errors": [{"code": 1003, "message": "unknown record query"}], "result": None}, 400)
                    return
                records = [record for record in read_records() if record["name"] == name and record["type"] == "A"]
                self.send_json({"success": True, "errors": [], "result": records})
                return
            self.send_json({"success": False, "errors": [{"code": 7003, "message": "not found"}], "result": None}, 404)

        def do_POST(self):
            prefix = f"{api_prefix}/zones/{zone_id}/dns_records"
            if urlsplit(self.path).path != prefix or not self.authorized():
                if urlsplit(self.path).path != prefix:
                    self.send_json({"success": False, "errors": [{"code": 7003, "message": "not found"}], "result": None}, 404)
                return
            body = self.read_body()
            if not valid_record(body, allowed_records):
                self.send_json({"success": False, "errors": [{"code": 1003, "message": "invalid record"}], "result": None}, 400)
                return
            records = read_records()
            record = {
                "id": "live-test-" + str(len(records) + 1), "type": "A", "name": body["name"],
                "content": str(ipaddress.IPv4Address(body["content"])), "ttl": 300, "proxied": False,
            }
            records.append(record)
            write_records(records)
            self.send_json({"success": True, "errors": [], "result": record}, 200)

        def do_PUT(self):
            path = urlsplit(self.path).path
            prefix = f"{api_prefix}/zones/{zone_id}/dns_records/"
            if not path.startswith(prefix) or not self.authorized():
                if not path.startswith(prefix):
                    self.send_json({"success": False, "errors": [{"code": 7003, "message": "not found"}], "result": None}, 404)
                return
            record_id = path[len(prefix):]
            body = self.read_body()
            if not valid_record(body, allowed_records):
                self.send_json({"success": False, "errors": [{"code": 1003, "message": "invalid record"}], "result": None}, 400)
                return
            records = read_records()
            for record in records:
                if record["id"] == record_id:
                    record["name"] = body["name"]
                    record["content"] = str(ipaddress.IPv4Address(body["content"]))
                    write_records(records)
                    self.send_json({"success": True, "errors": [], "result": record})
                    return
            self.send_json({"success": False, "errors": [{"code": 81044, "message": "record not found"}], "result": None}, 404)

        def authorized(self):
            if self.headers.get("Authorization", "").startswith("Bearer "):
                return True
            self.send_json({"success": False, "errors": [{"code": 10000, "message": "authentication required"}], "result": None}, 403)
            return False

        def read_body(self):
            try:
                return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            except (ValueError, json.JSONDecodeError):
                return {}

        def send_text(self, text):
            payload = text.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, value, status=200):
            payload = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            return

    return Handler


def valid_record(body, allowed_records):
    if not isinstance(body, dict) or body.get("type") != "A" or body.get("name") not in allowed_records:
        return False
    try:
        ipaddress.IPv4Address(body["content"])
    except (KeyError, TypeError, ValueError):
        return False
    return True


def ensure_records():
    if not RECORDS.exists():
        write_records([])


def read_records():
    return json.loads(RECORDS.read_text())


def write_records(records):
    RECORDS.write_text(json.dumps(records, separators=(",", ":")) + "\n")
    RECORDS.chmod(0o600)


def read_configuration(path):
    with path.open() as stream:
        configuration = yaml.safe_load(stream)
    if not isinstance(configuration, dict) or not isinstance(configuration.get("private_cloud"), dict):
        raise ValueError("Configuration file does not contain private_cloud")
    return configuration


if __name__ == "__main__":
    main()
