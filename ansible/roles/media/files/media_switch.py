"""Serve a LAN-only page that scales the VPN-guarded media workloads to one or zero replicas."""

import html
import json
import os
import ssl
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WORKLOADS = ("media-vpn", "sonarr", "radarr", "prowlarr", "bazarr", "flaresolverr")
API = os.environ["KUBERNETES_API"] + "/apis/apps/v1/namespaces/media/deployments/"
ORIGIN = "https://" + os.environ["SWITCH_HOSTNAME"]
ACCOUNT = "/var/run/secrets/kubernetes.io/serviceaccount/"


def main():
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


def read_states():
    states = {}
    for name in WORKLOADS:
        deployment = request("GET", API + name)
        states[name] = (deployment["spec"].get("replicas", 0), deployment.get("status", {}).get("readyReplicas", 0))
    return states


def scale(replicas):
    for name in WORKLOADS:
        request("PATCH", API + name + "/scale", {"spec": {"replicas": replicas}})


def render(states):
    desired = {wanted for wanted, _ in states.values()}
    state = "On" if desired == {1} else "Off" if desired == {0} else "Mixed"
    action, label = ("off", "Turn off") if state == "On" else ("on", "Turn on")
    rows = "".join(f"<tr><td>{html.escape(name)}</td><td>{ready}/{wanted}</td></tr>" for name, (wanted, ready) in states.items())
    return PAGE.format(state=state, action=action, label=label, rows=rows)


def request(method, url, body=None):
    with open(ACCOUNT + "token") as handle:
        token = handle.read().strip()
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/merge-patch+json"
    context = ssl.create_default_context(cafile=ACCOUNT + "ca.crt")
    with urllib.request.urlopen(urllib.request.Request(url, data, headers, method=method), timeout=10, context=context) as response:
        return json.load(response)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        body = render(read_states()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        # Browsers send Origin on form posts, so a foreign page cannot flip the switch through a LAN browser.
        if self.path not in ("/on", "/off") or self.headers.get("Origin") != ORIGIN:
            self.send_error(403)
            return
        scale(1 if self.path == "/on" else 0)
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format, *args):
        pass


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>Media switch</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 28rem; margin: 3rem auto; padding: 0 1rem; color: #1f2328; background: #f6f8fa; }}
button {{ font-size: 1.1rem; padding: .7rem 1.6rem; border: 0; border-radius: .5rem; color: #fff; background: #0969da; cursor: pointer; }}
table {{ width: 100%; margin-top: 2rem; border-collapse: collapse; }}
td {{ padding: .35rem 0; border-bottom: 1px solid #d0d7de; }}
td + td {{ text-align: right; }}
@media (prefers-color-scheme: dark) {{ body {{ color: #e6edf3; background: #0d1117; }} td {{ border-color: #30363d; }} }}
</style>
</head>
<body>
<h1>Media services: {state}</h1>
<form method="post" action="/{action}"><button>{label}</button></form>
<table>{rows}</table>
</body>
</html>
"""


if __name__ == "__main__":
    main()
