#!/usr/bin/env python3
"""Issue test certificates through a local ACME protocol endpoint."""

from http.server import ThreadingHTTPServer
from pathlib import Path
import ssl
import sys
from urllib.parse import urlsplit

import yaml

from acme_helpers import make_handler


def main():
    cloud = yaml.safe_load(Path(sys.argv[1]).read_text())["private_cloud"]
    endpoint = urlsplit(cloud["networking"]["acme_directory_url"])
    if endpoint.scheme != "https" or not endpoint.port:
        raise ValueError("The local ACME mock requires HTTPS with an explicit port")
    artifacts = Path("/var/lib/private-cloud-live-test")
    names = {cloud[key]["hostname"] for key in ("stalwart", "media", "onlyoffice", "opencloud", "grist", "affine", "immich", "logging")}
    names.add(cloud["networking"]["zabbix_hostname"])
    base = f"https://{endpoint.netloc}"
    server = ThreadingHTTPServer(("0.0.0.0", endpoint.port), make_handler(base, names, artifacts))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(artifacts / "server.crt", artifacts / "server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
