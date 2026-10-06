#!/usr/bin/env python3
"""Run bounded live fixtures against the mock OpenVPN and AmneziaWG peers."""

import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

from mock_helpers import ARTIFACTS, kubectl, kubectl_json, start_openvpn, stop_openvpn


CLIENT_NAME = "live-test-amneziawg-client"
CLIENT_SECRET = "live-test-amneziawg-client"
CLIENT_POLICY = "live-test-amneziawg-client"
CA_SECRET = "live-test-amneziawg-ca"
GATEWAY_POLICY = "private-cloud-live-test-vpn-mock-egress"
FIXTURE_LABEL = "private-cloud.example/live-test-amwg-client"
MOCK_PUBLIC_IP = "198.51.100.254"
PYTHON_IMAGE = "python:3.14-alpine@sha256:c6ead215bfd31f1e433d968853b7a769989117115b728874824e6c0a27cb96fc"


def validate_killswitch(configuration):
    cloud = configuration["private_cloud"]
    public_ip_url = cloud["networking"]["public_ip_url"]
    parsed_url = urlsplit(public_ip_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ValueError("The configured public-IP URL must use HTTPS")
    port = parsed_url.port or 443
    host_ip = str(ipaddress.IPv4Address(cloud["networking"]["traefik_internal_ip"]))
    expected_ip = host_ip
    mock_ip = str(ipaddress.IPv4Address(MOCK_PUBLIC_IP))
    ca_file = ARTIFACTS / "ca.crt"
    if not ca_file.is_file():
        raise RuntimeError("Prepare and trust the local mock CA before running the VPN fixture")
    require_rollout("media", "media-vpn", 30)
    require_rollout("media", "qbittorrent", 30)
    rule_handle = None
    mock_address_added = False
    gateway_policy_added = False
    down_started = None
    restored = False
    ca_installed = False
    try:
        install_qbittorrent_ca(ca_file)
        ca_installed = True
        # A reserved, temporary fixture IP avoids the direct route to the VPN server host.
        add_fixture_address(mock_ip)
        mock_address_added = True
        rule_handle = allow_mock_ip_probe(port, mock_ip)
        add_gateway_mock_policy(mock_ip, port)
        gateway_policy_added = True
        require_route_through_tun(mock_ip)
        require_gateway_route_through_tun(mock_ip)
        try:
            baseline = qbittorrent_public_ip(public_ip_url, parsed_url.hostname, port, mock_ip, 5)
        except subprocess.CalledProcessError as error:
            detail = (error.stderr or "").strip()
            raise RuntimeError(f"qBittorrent could not reach the mock public-IP endpoint: {detail}") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("qBittorrent timed out reaching the mock public-IP endpoint") from None
        if baseline != expected_ip:
            raise RuntimeError("qBittorrent did not reach the configured mock public-IP service through its VPN")

        tunnel_test_started = time.monotonic()
        run_kubectl([
            "exec", "-n", "media", "deployment/media-vpn", "-c", "openvpn", "--",
            "ip", "link", "set", "dev", "tun0", "down",
        ])
        try:
            require_qbittorrent_blocked(public_ip_url, parsed_url.hostname, port, mock_ip, 4)
        finally:
            run_kubectl([
                "exec", "-n", "media", "deployment/media-vpn", "-c", "openvpn", "--",
                "ip", "link", "set", "dev", "tun0", "up",
            ])
        wait_gateway_healthy(90)
        wait_for_public_ip(public_ip_url, parsed_url.hostname, port, mock_ip, expected_ip, 90)
        tunnel_restore = time.monotonic() - tunnel_test_started
        if tunnel_restore >= 100:
            raise RuntimeError("The bounded tun0 kill-switch probe exceeded its 100-second restoration window")

        pid_file = ARTIFACTS / "openvpn-server.pid"
        stopped_pid = int(pid_file.read_text().strip()) if pid_file.exists() else None
        stop_openvpn()
        down_started = time.monotonic()
        wait_openvpn_stopped(stopped_pid, 5)
        try:
            require_qbittorrent_blocked(public_ip_url, parsed_url.hostname, port, mock_ip, 4)
        finally:
            start_openvpn(configuration)
            restored = True

        wait_gateway_healthy(45)
        recovery_budget = max(1, 60 - (time.monotonic() - down_started))
        recovery = wait_for_public_ip(public_ip_url, parsed_url.hostname, port, mock_ip, expected_ip, recovery_budget)
        outage_seconds = time.monotonic() - down_started
        if outage_seconds >= 60:
            raise RuntimeError("The mock OpenVPN gateway did not restore service within the 60-second bound")
        print(json.dumps({
            "fixture": "openvpn-killswitch",
            "baseline": "passed",
            "tun0_down": "blocked",
            "remote_gateway_loss": "blocked",
            "recovery": "passed",
            "tun0_restore_seconds": round(tunnel_restore, 2),
            "mock_restore_seconds": round(outage_seconds, 2),
            "public_ip": recovery,
        }, separators=(",", ":")))
    finally:
        if not restored and down_started is not None:
            start_openvpn(configuration)
        if rule_handle:
            remove_input_rule(rule_handle)
        if gateway_policy_added:
            kubectl(["delete", "networkpolicy", GATEWAY_POLICY, "-n", "media", "--ignore-not-found=true"])
        if mock_address_added:
            remove_fixture_address(mock_ip)
        if ca_installed:
            remove_qbittorrent_ca()


def validate_amneziawg_peer(configuration, credential_path=None):
    cloud = configuration["private_cloud"]
    networking = cloud["networking"]
    amnezia = networking["amneziawg"]
    peers = amnezia.get("peers", [])
    credentials = read_credentials(credential_path)
    matching_peers = [
        peer for peer in peers
        if peer.get("public_key") == credentials["amneziawg_peer_public_key"]
    ]
    if len(matching_peers) != 1:
        raise ValueError("The root-only test key must match exactly one globally configured AmneziaWG peer")
    peer = matching_peers[0]
    tunnel = ipaddress.ip_network(amnezia["tunnel_cidr"], strict=False)
    peer_address = ipaddress.ip_address(peer["address"])
    if peer_address not in tunnel:
        raise ValueError("The configured AmneziaWG peer address is outside its tunnel CIDR")

    server_config = read_server_configuration()
    if peer["public_key"] not in server_config:
        raise RuntimeError("The installed AmneziaWG server config does not contain the configured peer")

    server_public_key = kubectl([
        "exec", "-n", "network-access", "deployment/amneziawg", "--", "awg", "show", "awg0", "public-key",
    ], capture=True).strip()
    pod_list = kubectl_json([
        "get", "pods", "-n", "network-access", "-l", "app.kubernetes.io/name=amneziawg", "-o", "json",
    ])
    server_pods = [pod for pod in pod_list.get("items", []) if pod.get("status", {}).get("phase") == "Running"]
    if len(server_pods) != 1 or not server_pods[0].get("status", {}).get("podIP"):
        raise RuntimeError("The installed AmneziaWG server pod has no unique running endpoint")
    server_pod_ip = server_pods[0]["status"]["podIP"]
    listen_port = int(amnezia["listen_port"])
    host_ip = str(ipaddress.IPv4Address(networking["traefik_internal_ip"]))
    hostname = cloud["media"]["hostname"].rstrip(".")
    ca_file = ARTIFACTS / "ca.crt"
    if not ca_file.is_file():
        raise RuntimeError("Prepare the local mock CA before running the AmneziaWG peer fixture")

    client_config = make_client_config(
        server_config,
        credentials["amneziawg_peer_private_key"],
        server_public_key,
        str(peer_address),
        server_pod_ip,
        listen_port,
        host_ip,
    )
    config_file = ARTIFACTS / "amneziawg-client-fixture.conf"
    config_file.write_text(client_config)
    os.chmod(config_file, 0o600)
    created = []
    try:
        created.extend([("secret", CLIENT_SECRET), ("secret", CA_SECRET)])
        create_fixture_secrets(config_file, ca_file)
        created.append(("networkpolicy", CLIENT_POLICY))
        apply_fixture_policy(server_pod_ip, listen_port)
        created.append(("pod", CLIENT_NAME))
        create_client_pod(hostname, host_ip, server_pod_ip, listen_port)
        wait_for_pod(CLIENT_NAME, 90)

        handshake_age = wait_for_handshake(peer["public_key"], 45)
        probe = probe_amneziawg_path(hostname, host_ip)
        if probe["http_status"] < 200 or probe["http_status"] >= 600:
            raise RuntimeError("The AmneziaWG peer received an invalid HTTP response through the allowed HTTPS path")
        if probe["tcp_22"] != "blocked":
            raise RuntimeError("The AmneziaWG peer reached TCP 22 outside its configured access")
        print(json.dumps({
            "fixture": "amneziawg-peer",
            "peer": peer.get("name", "configured-peer"),
            "handshake_age_seconds": handshake_age,
            "https_status": probe["http_status"],
            "tcp_22": "blocked",
        }, separators=(",", ":")))
    finally:
        cleanup_fixture_resources(created)
        config_file.unlink(missing_ok=True)


def make_client_config(server_config, client_private_key, server_public_key, client_address, endpoint, port, allowed_address):
    obfuscation_names = {"Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"}
    obfuscation = []
    in_interface = False
    for line in server_config.splitlines():
        stripped = line.strip()
        if stripped == "[Interface]":
            in_interface = True
            continue
        if stripped.startswith("["):
            in_interface = False
        if in_interface and "=" in stripped:
            name, value = (part.strip() for part in stripped.split("=", 1))
            if name in obfuscation_names:
                obfuscation.append(f"{name} = {value}")
    return "\n".join([
        "[Interface]",
        f"Address = {client_address}/32",
        f"PrivateKey = {client_private_key}",
        *obfuscation,
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
        f"Endpoint = {endpoint}:{port}",
        f"AllowedIPs = {allowed_address}/32",
        "PersistentKeepalive = 10",
        "",
    ])


def create_fixture_secrets(config_file, ca_file):
    for name, source in ((CLIENT_SECRET, config_file), (CA_SECRET, ca_file)):
        manifest = kubectl([
            "create", "secret", "generic", name, "-n", "network-access",
            f"--from-file={'awg0.conf' if name == CLIENT_SECRET else 'ca-bundle.crt'}={source}",
            "--dry-run=client", "-o", "yaml",
        ], capture=True)
        kubectl(["apply", "-f", "-"], input_text=manifest)


def apply_fixture_policy(server_pod_ip, port):
    manifest = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": CLIENT_POLICY, "namespace": "network-access"},
        "spec": {
            "podSelector": {"matchLabels": {FIXTURE_LABEL: "true"}},
            "policyTypes": ["Egress"],
            "egress": [{
                "to": [{"podSelector": {"matchLabels": {"app.kubernetes.io/name": "amneziawg"}}}],
                "ports": [{"protocol": "UDP", "port": port}],
            }],
        },
    }
    kubectl(["apply", "-f", "-"], input_text=json.dumps(manifest))


def create_client_pod(hostname, host_ip, endpoint_ip, listen_port):
    image = kubectl([
        "get", "deployment", "amneziawg", "-n", "network-access",
        "-o", "jsonpath={.spec.template.spec.containers[0].image}",
    ], capture=True).strip()
    manifest = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": CLIENT_NAME,
            "namespace": "network-access",
            "labels": {FIXTURE_LABEL: "true"},
        },
        "spec": {
            "automountServiceAccountToken": False,
            "restartPolicy": "Never",
            "hostAliases": [{"ip": host_ip, "hostnames": [hostname]}],
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [
                {
                    "name": "amneziawg",
                    "image": image,
                    "command": ["/bin/bash", "-ceu"],
                    "args": ["awg-quick up /etc/amneziawg/awg0.conf; trap 'awg-quick down /etc/amneziawg/awg0.conf' TERM INT EXIT; sleep infinity & wait $!"],
                    "securityContext": {
                        "runAsUser": 0,
                        "runAsGroup": 0,
                        "allowPrivilegeEscalation": False,
                        "capabilities": {"drop": ["ALL"], "add": ["NET_ADMIN"]},
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "resources": {"requests": {"cpu": "20m", "memory": "64Mi"}, "limits": {"memory": "128Mi"}},
                    "volumeMounts": [{"name": "amneziawg-config", "mountPath": "/etc/amneziawg", "readOnly": True}],
                },
                {
                    "name": "probe",
                    "image": PYTHON_IMAGE,
                    "command": ["python3", "-c", "import time; time.sleep(3600)"],
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                        "runAsGroup": 1000,
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "resources": {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"memory": "64Mi"}},
                    "volumeMounts": [{"name": "test-ca", "mountPath": "/etc/private-cloud-test-ca", "readOnly": True}],
                },
            ],
            "volumes": [
                {"name": "amneziawg-config", "secret": {"secretName": CLIENT_SECRET, "defaultMode": 0o400}},
                {"name": "test-ca", "secret": {"secretName": CA_SECRET, "defaultMode": 0o444}},
            ],
        },
    }
    kubectl(["apply", "-f", "-"], input_text=json.dumps(manifest))


def wait_for_pod(name, seconds):
    kubectl(["wait", "--for=condition=Ready", f"pod/{name}", "-n", "network-access", f"--timeout={seconds}s"])


def wait_for_handshake(public_key, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        output = kubectl([
            "exec", "-n", "network-access", "deployment/amneziawg", "--",
            "awg", "show", "awg0", "latest-handshakes",
        ], capture=True)
        for line in output.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] == public_key:
                timestamp = int(fields[1])
                if timestamp > 0:
                    age = max(0, int(time.time()) - timestamp)
                    if age <= 20:
                        return age
        time.sleep(1)
    raise RuntimeError("The configured AmneziaWG peer did not complete a recent handshake")


def probe_amneziawg_path(hostname, host_ip):
    script = r'''
import http.client
import json
import socket
import ssl
import sys

hostname = sys.argv[1]
host_ip = sys.argv[2]
context = ssl.create_default_context(cafile="/etc/private-cloud-test-ca/ca-bundle.crt")
connection = http.client.HTTPSConnection(hostname, 443, context=context, timeout=8)
connection.request("GET", "/System/Info/Public", headers={"Host": hostname})
response = connection.getresponse()
status = response.status
response.read(4096)
connection.close()
try:
    socket.create_connection((host_ip, 22), timeout=3).close()
except (OSError, TimeoutError):
    blocked = True
else:
    blocked = False
print(json.dumps({"http_status": status, "tcp_22": "blocked" if blocked else "open"}))
'''
    try:
        output = kubectl([
            "exec", "-n", "network-access", CLIENT_NAME, "-c", "probe", "--",
            "python3", "-c", script, hostname, host_ip,
        ], capture=True)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()
        raise RuntimeError(f"The AmneziaWG path probe failed: {detail[:4000]}") from None
    try:
        return json.loads(output.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError("The AmneziaWG path probe returned invalid output") from error


def cleanup_fixture_resources(created):
    for kind, name in reversed(created):
        kubectl(["delete", kind, name, "-n", "network-access", "--ignore-not-found=true"])
    if created:
        try:
            kubectl(["wait", "--for=delete", f"pod/{CLIENT_NAME}", "-n", "network-access", "--timeout=30s"])
        except subprocess.CalledProcessError:
            pass


def read_server_configuration():
    secret = kubectl_json(["get", "secret", "amneziawg-config", "-n", "network-access", "-o", "json"])
    return base64.b64decode(secret["data"]["awg0.conf"]).decode()


def read_credentials(credential_path=None):
    path = credential_path or ARTIFACTS / "credentials.json"
    values = json.loads(Path(path).read_text())
    required = {"amneziawg_peer_private_key", "amneziawg_peer_public_key"}
    if not required.issubset(values):
        raise RuntimeError("The root-only test credential file lacks the configured AmneziaWG peer")
    return values


def install_qbittorrent_ca(ca_file):
    result = subprocess.run([
        "k0s", "kubectl", "exec", "-i", "-n", "media", "deployment/qbittorrent", "-c", "qbittorrent", "--",
        "sh", "-c", "umask 077; cat > /tmp/private-cloud-live-test-ca.crt",
    ], input=ca_file.read_bytes(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return result


def remove_qbittorrent_ca():
    subprocess.run([
        "k0s", "kubectl", "exec", "-n", "media", "deployment/qbittorrent", "-c", "qbittorrent", "--",
        "rm", "-f", "/tmp/private-cloud-live-test-ca.crt",
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def qbittorrent_public_ip(url, hostname, port, host_ip, timeout):
    resolve = f"{hostname}:{port}:{host_ip}"
    result = subprocess.run([
        "k0s", "kubectl", "exec", "-n", "media", "deployment/qbittorrent", "-c", "qbittorrent", "--",
        "curl", "--noproxy", "*", "--silent", "--show-error", "--fail", "--connect-timeout", "2",
        "--max-time", str(timeout), "--cacert", "/tmp/private-cloud-live-test-ca.crt",
        "--resolve", resolve, url,
    ], check=True, capture_output=True, text=True, timeout=timeout + 5)
    return str(ipaddress.IPv4Address(result.stdout.strip()))


def wait_for_public_ip(url, hostname, port, host_ip, expected, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            actual = qbittorrent_public_ip(url, hostname, port, host_ip, 5)
        except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(1)
            continue
        if actual == expected:
            return actual
        time.sleep(1)
    raise RuntimeError("qBittorrent did not recover public-IP access after the OpenVPN mock restarted")


def wait_gateway_healthy(seconds):
    deadline = time.monotonic() + seconds
    last_error = None
    while time.monotonic() < deadline:
        result = subprocess.run([
            "k0s", "kubectl", "exec", "-n", "media", "deployment/media-vpn", "-c", "openvpn", "--",
            "/gluetun-entrypoint", "healthcheck",
        ], capture_output=True, text=True)
        if result.returncode == 0:
            return
        last_error = result.stderr.strip()
        time.sleep(1)
    raise RuntimeError(f"The media OpenVPN gateway did not become healthy after restoration: {last_error}")


def require_rollout(namespace, deployment, seconds):
    kubectl([
        "rollout", "status", f"deployment/{deployment}", "-n", namespace, f"--timeout={seconds}s",
    ])


def allow_mock_ip_probe(port, destination):
    server_config = (ARTIFACTS / "openvpn-server.conf").read_text()
    device_match = re.search(r"(?m)^dev\s+(\S+)\s*$", server_config)
    network_match = re.search(r"(?m)^server\s+(\S+)\s+(\S+)\s*$", server_config)
    if not device_match or not network_match:
        raise RuntimeError("The mock OpenVPN server config lacks its fixture interface or subnet")
    network = ipaddress.ip_network(f"{network_match.group(1)}/{network_match.group(2)}", strict=False)
    if network.version != 4:
        raise RuntimeError("The mock OpenVPN network must be IPv4")
    comment = "private-cloud-live-test-vpn-fixture"
    subprocess.run([
        "nft", "add", "rule", "inet", "private_cloud", "input",
        "iifname", device_match.group(1), "ip", "saddr", str(network),
        "ip", "daddr", destination,
        "tcp", "dport", str(port), "accept", "comment", comment,
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    rules = subprocess.run(
        ["nft", "-a", "list", "chain", "inet", "private_cloud", "input"],
        check=True, capture_output=True, text=True,
    ).stdout
    matches = re.findall(rf'comment "{re.escape(comment)}" # handle (\d+)', rules)
    if not matches:
        remove_fixture_address(destination)
        raise RuntimeError("Could not identify the temporary mock-IP firewall rule for cleanup")
    return matches[-1]


def add_fixture_address(address):
    result = subprocess.run(
        ["ip", "-j", "address", "show", "dev", "lo"],
        check=True, capture_output=True, text=True,
    )
    existing = {
        entry["local"]
        for interface in json.loads(result.stdout)
        for entry in interface.get("addr_info", [])
        if entry.get("family") == "inet"
    }
    if address in existing:
        raise RuntimeError("The VPN fixture address is already assigned to host loopback")
    subprocess.run([
        "ip", "address", "add", f"{address}/32", "dev", "lo",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def remove_fixture_address(address):
    subprocess.run([
        "ip", "address", "del", f"{address}/32", "dev", "lo",
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def require_route_through_tun(address):
    output = kubectl([
        "exec", "-n", "media", "deployment/qbittorrent", "-c", "vpn-route", "--",
        "ip", "route", "get", address,
    ], capture=True)
    if not re.search(r"\bdev\s+tun0\b", output):
        raise RuntimeError("The temporary public mock address does not traverse qBittorrent's tun0 route")


def require_gateway_route_through_tun(address):
    output = kubectl([
        "exec", "-n", "media", "deployment/media-vpn", "-c", "openvpn", "--",
        "ip", "route", "get", address,
    ], capture=True)
    if not re.search(r"\bdev\s+tun0\b", output):
        raise RuntimeError("The temporary public mock address does not traverse the OpenVPN gateway's tun0 route")


def add_gateway_mock_policy(address, port):
    result = subprocess.run([
        "k0s", "kubectl", "get", "networkpolicy", GATEWAY_POLICY, "-n", "media", "-o", "name",
    ], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        raise RuntimeError("A prior VPN fixture egress policy is still present")
    if result.returncode not in {0, 1}:
        raise RuntimeError("Could not inspect the media namespace before creating the VPN fixture policy")
    manifest = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": GATEWAY_POLICY, "namespace": "media"},
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "media-vpn"}},
            "policyTypes": ["Egress"],
            "egress": [{
                "to": [{"ipBlock": {"cidr": f"{address}/32"}}],
                "ports": [{"protocol": "TCP", "port": port}],
            }],
        },
    }
    kubectl(["apply", "-f", "-"], input_text=json.dumps(manifest))


def remove_input_rule(handle):
    subprocess.run([
        "nft", "delete", "rule", "inet", "private_cloud", "input", "handle", str(handle),
    ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_openvpn_stopped(pid, seconds):
    if pid is None:
        raise RuntimeError("The mock OpenVPN server has no recorded process to stop")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, ValueError):
            return
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists() and stat.read_text().split()[2] == "Z":
            return
        time.sleep(0.1)
    raise RuntimeError("The OpenVPN mock did not stop before the bounded kill-switch probe")


def require_qbittorrent_blocked(url, hostname, port, host_ip, timeout):
    try:
        qbittorrent_public_ip(url, hostname, port, host_ip, timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return
    raise RuntimeError("qBittorrent reached the configured mock public-IP endpoint without its VPN path")


def run_kubectl(arguments):
    subprocess.run(["k0s", "kubectl", *arguments], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
