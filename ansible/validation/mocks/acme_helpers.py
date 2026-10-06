"""Local ACME fixtures; ownership challenges and JWS signatures are mocked."""

import base64
from http.server import BaseHTTPRequestHandler
import json
import secrets
import subprocess
from urllib.parse import urlsplit


def make_handler(base, allowed_names, artifacts):
    orders = {}

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            self.respond({}, 200)

        def do_GET(self):
            self.dispatch({})

        def do_POST(self):
            envelope = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            payload = envelope.get("payload", "")
            body = json.loads(decode(payload)) if payload else {}
            self.dispatch(body)

        def dispatch(self, body):
            path = urlsplit(self.path).path
            if path == "/directory":
                self.respond({"newNonce": base + "/nonce", "newAccount": base + "/account", "newOrder": base + "/orders", "revokeCert": base + "/revoke", "keyChange": base + "/key-change"})
            elif path == "/nonce":
                self.respond({}, 200)
            elif path.startswith("/account"):
                self.respond({"status": "valid", "contact": body.get("contact", []), "orders": base + "/orders"}, 201, base + "/account/1")
            elif path == "/orders":
                names = {item["value"] for item in body["identifiers"]}
                if not names or not names <= allowed_names:
                    self.respond({"type": "urn:ietf:params:acme:error:rejectedIdentifier", "detail": "Identifier is outside the configured trial hostnames"}, 400)
                    return
                identifier = secrets.token_hex(8)
                orders[identifier] = {"status": "ready", "identifiers": body["identifiers"], "authorizations": [base + "/authorization/" + name for name in sorted(names)], "finalize": base + "/finalize/" + identifier}
                self.respond(orders[identifier], 201, base + "/order/" + identifier)
            elif path.startswith("/authorization/"):
                name = path.removeprefix("/authorization/")
                self.respond({"status": "valid", "identifier": {"type": "dns", "value": name}, "challenges": []})
            elif path.startswith("/finalize/"):
                identifier = path.rsplit("/", 1)[-1]
                csr = artifacts / (identifier + ".csr")
                certificate = artifacts / (identifier + ".crt")
                csr.write_bytes(decode(body["csr"]))
                subprocess.run(["openssl", "x509", "-req", "-inform", "DER", "-in", str(csr), "-CA", str(artifacts / "ca.crt"), "-CAkey", str(artifacts / "ca.key"), "-set_serial", "0x" + identifier, "-days", "90", "-copy_extensions", "copy", "-out", str(certificate)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                orders[identifier].update(status="valid", certificate=base + "/certificate/" + identifier)
                self.respond(orders[identifier])
            elif path.startswith("/order/"):
                self.respond(orders[path.rsplit("/", 1)[-1]])
            elif path.startswith("/certificate/"):
                identifier = path.rsplit("/", 1)[-1]
                chain = (artifacts / (identifier + ".crt")).read_bytes() + (artifacts / "ca.crt").read_bytes()
                self.respond(chain, content_type="application/pem-certificate-chain")
            else:
                self.respond({"type": "urn:ietf:params:acme:error:malformed"}, 404)

        def respond(self, body, status=200, location=None, content_type="application/json"):
            encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Replay-Nonce", secrets.token_urlsafe(24))
            self.send_header("Link", '<' + base + '/directory>;rel="index"')
            if location:
                self.send_header("Location", location)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(encoded)

        def log_message(self, format, *arguments):
            return

    return Handler


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
