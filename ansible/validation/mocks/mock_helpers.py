#!/usr/bin/env python3
"""Prepare local service mocks for a disposable live installation."""

import argparse
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import ssl
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit

import yaml

from smtp_delivery import deliver_message, envelope_address
from smtp_listener import serve_sniffed


ARTIFACTS = Path("/var/lib/private-cloud-live-test")
VPN_NETWORK = "10.253.0.0/24"
# OpenObserve trusts only compiled-in public roots, so the trial sends its mail to the local relay without TLS.
OPENOBSERVE_TRIAL_SMTP_ENCRYPTION = "none"


def restore_mocks(configuration, configuration_path):
    prepare(configuration)
    install_host_trust()
    start_openvpn(configuration)
    start_smtp(configuration)
    start_cloudflare(configuration, configuration_path)
    start_acme(configuration, configuration_path)
    install_cluster_dns(configuration)
    install_cluster_trust()
    install_traefik_certificate()
    allow_cloudflare(configuration)
    allow_acme(configuration)
    enable_stalwart_relay(configuration)



def prepare(configuration):
    cloud = configuration["private_cloud"]
    endpoint = cloud["media"]["openvpn"]
    endpoint_ip = str(ipaddress.IPv4Address(endpoint["endpoint_ip"]))
    endpoint_port = int(endpoint["endpoint_port"])
    endpoint_protocol = endpoint["endpoint_protocol"].lower()
    if endpoint_ip in {"127.0.0.1", "0.0.0.0"} or not 1 <= endpoint_port <= 65535:
        raise ValueError("The mock OpenVPN endpoint must be a routable host IPv4 address and valid port")
    if endpoint_protocol not in {"tcp", "udp"}:
        raise ValueError("The mock OpenVPN endpoint protocol must be TCP or UDP")

    for executable in ("openssl", "openvpn"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required mock dependency is unavailable: {executable}")

    credentials = read_or_create_credentials(cloud)
    create_certificates(cloud, endpoint_ip)
    create_openvpn_files(endpoint_ip, endpoint_port, endpoint_protocol, credentials)
    write_host_mapping(configuration)
    print(json.dumps({
        "artifacts": str(ARTIFACTS),
        "openvpn_profile": str(ARTIFACTS / "client.ovpn"),
        "mock_credentials": str(ARTIFACTS / "mock-credentials.json"),
        "ca_certificate": str(ARTIFACTS / "ca.crt"),
        "openvpn_endpoint": f"{endpoint_ip}:{endpoint_port}/{endpoint_protocol.upper()}",
    }, separators=(",", ":")))


def start_openvpn(configuration):
    config = ARTIFACTS / "openvpn-server.conf"
    pid_file = ARTIFACTS / "openvpn-server.pid"
    log_file = ARTIFACTS / "openvpn-server.log"
    if pid_file.exists() and process_running(pid_file):
        return
    if not config.exists():
        prepare(configuration)
    add_vpn_nat()
    previous_forwarding = Path("/proc/sys/net/ipv4/ip_forward").read_text().strip()
    (ARTIFACTS / "ip-forward.previous").write_text(previous_forwarding + "\n")
    subprocess.run(["sysctl", "-w", "net.ipv4.ip_forward=1"], check=True, stdout=subprocess.DEVNULL)
    log_file.write_text("")
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            ["openvpn", "--config", str(config), "--writepid", str(pid_file)],
            cwd=ARTIFACTS,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"OpenVPN mock exited early; inspect {log_file}")
        if log_file.exists() and "Initialization Sequence Completed" in log_file.read_text(errors="replace"):
            return
        time.sleep(0.1)
    raise RuntimeError(f"OpenVPN mock did not become ready; inspect {log_file}")


def stop_openvpn():
    pid_file = ARTIFACTS / "openvpn-server.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
        except ProcessLookupError:
            pass
        pid_file.unlink(missing_ok=True)
    subprocess.run(["nft", "delete", "table", "ip", "private_cloud_live_test"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    previous = ARTIFACTS / "ip-forward.previous"
    if previous.exists():
        value = previous.read_text().strip()
        subprocess.run(["sysctl", "-w", f"net.ipv4.ip_forward={value}"], check=False, stdout=subprocess.DEVNULL)
        previous.unlink(missing_ok=True)


def install_host_trust():
    source = ARTIFACTS / "ca.crt"
    target = Path("/usr/local/share/ca-certificates/private-cloud-live-test.crt")
    if not source.is_file():
        raise RuntimeError("Run prepare before installing the test CA")
    target.write_bytes(source.read_bytes())
    subprocess.run(["update-ca-certificates"], check=True, stdout=subprocess.DEVNULL)


def install_cluster_trust():
    bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    if not bundle.is_file():
        raise RuntimeError("Install host trust before injecting the test CA into workloads")
    namespaces = ["private-cloud", "edge", "media", "observability", "dns-system"]
    for namespace in namespaces:
        secret_yaml = kubectl(["create", "secret", "generic", "private-cloud-live-test-ca", "-n", namespace,
                               f"--from-file=ca-bundle.crt={bundle}", "--dry-run=client", "-o", "yaml"], capture=True)
        kubectl(["apply", "-f", "-"], input_text=secret_yaml)
    for kind in ("deployments", "statefulsets"):
        objects = kubectl_json(["get", kind, "--all-namespaces", "-o", "json"])
        for item in objects.get("items", []):
            namespace = item["metadata"]["namespace"]
            name = item["metadata"]["name"]
            required_workload = (
                kind == "deployments" and ((namespace == "edge" and name in {"traefik", "forward-auth"}) or (namespace == "private-cloud" and name in {"opencloud", "onlyoffice", "grist", "affine", "immich", "zabbix-server", "zabbix-web"}) or (namespace == "observability" and name == "openobserve"))
            ) or (
                kind == "statefulsets" and namespace == "private-cloud" and name == "stalwart"
            )
            if not required_workload:
                continue
            patch = {
                "spec": {"template": {"metadata": {"annotations": {
                    "private-cloud-live-test/ca-sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
                }}, "spec": {
                    "volumes": [{"name": "private-cloud-live-test-ca", "secret": {"secretName": "private-cloud-live-test-ca"}}],
                    "containers": [{
                        "name": container["name"],
                        "env": [
                            {"name": "SSL_CERT_FILE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                            {"name": "CURL_CA_BUNDLE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                            {"name": "REQUESTS_CA_BUNDLE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                            {"name": "NODE_EXTRA_CA_CERTS", "value": "/etc/ssl/certs/ca-certificates.crt"},
                            {"name": "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", "value": "/etc/ssl/certs/ca-certificates.crt"},
                            *trial_smtp_environment(namespace, name, container),
                        ],
                        "volumeMounts": [{"name": "private-cloud-live-test-ca", "mountPath": "/etc/ssl/certs/ca-certificates.crt", "subPath": "ca-bundle.crt", "readOnly": True}],
                    } for container in item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])],
                }}}
            }
            if patch["spec"]["template"]["spec"]["containers"]:
                kubectl(["patch", kind[:-1], name, "-n", namespace, "--type", "strategic", "-p", json.dumps(patch)])


def trial_smtp_environment(namespace, name, container):
    configured = any(entry["name"] == "ZO_SMTP_ENCRYPTION" for entry in container.get("env", []))
    if namespace == "observability" and name == "openobserve" and configured:
        return [{"name": "ZO_SMTP_ENCRYPTION", "value": OPENOBSERVE_TRIAL_SMTP_ENCRYPTION}]
    return []


def install_cluster_dns(configuration):
    cloud = configuration["private_cloud"]
    address = cloud["networking"]["traefik_internal_ip"]
    names = configured_hostnames(cloud)
    relay_host = cloud.get("stalwart", {}).get("relay_host")
    if relay_host:
        names.add(relay_host.rstrip("."))
    entries = "\n".join(f"{address} {name}" for name in sorted(names))
    configmaps = kubectl_json(["get", "configmaps", "--all-namespaces", "-o", "json"])
    candidates = [item for item in configmaps["items"] if item["metadata"]["namespace"] == "kube-system" and "Corefile" in item.get("data", {})]
    if len(candidates) != 1:
        raise RuntimeError("Expected one CoreDNS ConfigMap containing Corefile")
    configmap = candidates[0]
    corefile = configmap["data"]["Corefile"]
    marker = "# BEGIN private-cloud-live-test DNS"
    if marker in corefile:
        start = corefile.index(marker)
        end = corefile.index("# END private-cloud-live-test DNS", start) + len("# END private-cloud-live-test DNS")
        corefile = corefile[:start] + corefile[end:]
    block = f"{marker}\nhosts {{\n{entries}\n  fallthrough\n}}\n# END private-cloud-live-test DNS\n"
    corefile = insert_hosts_plugin(corefile, block)
    save_original("coredns-corefile.json", {"namespace": configmap["metadata"]["namespace"], "name": configmap["metadata"]["name"], "Corefile": configmap["data"]["Corefile"]})
    kubectl(["patch", "configmap", configmap["metadata"]["name"], "-n", configmap["metadata"]["namespace"],
             "--type", "merge", "-p", json.dumps({"data": {"Corefile": corefile}})])
    restart_coredns(configmap["metadata"]["namespace"])


def install_traefik_certificate():
    certificate = ARTIFACTS / "server.crt"
    private_key = ARTIFACTS / "server.key"
    if not certificate.is_file() or not private_key.is_file():
        raise RuntimeError("Run prepare before injecting the Traefik certificate")
    secret_yaml = kubectl(["create", "secret", "tls", "private-cloud-live-test-tls", "-n", "edge",
                           f"--cert={certificate}", f"--key={private_key}", "--dry-run=client", "-o", "yaml"], capture=True)
    kubectl(["apply", "-f", "-"], input_text=secret_yaml)
    configmap = kubectl_json(["get", "configmap", "traefik-dynamic", "-n", "edge", "-o", "json"])
    dynamic = configmap["data"]["tcp.yaml"]
    save_original("traefik-dynamic.json", {"namespace": "edge", "name": "traefik-dynamic", "tcp.yaml": dynamic})
    dynamic = remove_marked_block(dynamic, "# BEGIN private-cloud-live-test TLS", "# END private-cloud-live-test TLS")
    dynamic += "\n# BEGIN private-cloud-live-test TLS\ntls:\n  certificates:\n    - certFile: /etc/traefik/live-test/tls.crt\n      keyFile: /etc/traefik/live-test/tls.key\n# END private-cloud-live-test TLS\n"
    kubectl(["patch", "configmap", "traefik-dynamic", "-n", "edge", "--type", "merge",
             "-p", json.dumps({"data": {"tcp.yaml": dynamic}})])
    deployment = kubectl_json(["get", "deployment", "traefik", "-n", "edge", "-o", "json"])
    patch = {
        "spec": {"template": {"spec": {
            "volumes": [{"name": "private-cloud-live-test-tls", "secret": {"secretName": "private-cloud-live-test-tls"}}],
            "containers": [{"name": "traefik", "volumeMounts": [{"name": "private-cloud-live-test-tls", "mountPath": "/etc/traefik/live-test", "readOnly": True}]}],
        }}}
    }
    kubectl(["patch", "deployment", "traefik", "-n", "edge", "--type", "strategic", "-p", json.dumps(patch)])
    kubectl(["rollout", "status", "deployment/traefik", "-n", "edge", "--timeout=180s"])


def enable_stalwart_relay(configuration):
    cloud = configuration["private_cloud"]
    relay_host = cloud["stalwart"]["relay_host"].rstrip(".")
    host_ip = cloud["media"]["openvpn"]["endpoint_ip"]
    port = int(cloud["stalwart"]["relay_port"])
    if not relay_host or not 1 <= port <= 65535:
        raise ValueError("Stalwart mock relay host or port is invalid")
    ca_bundle = Path("/etc/ssl/certs/ca-certificates.crt")
    if not ca_bundle.exists():
        raise RuntimeError("Install host trust before enabling the Stalwart mock relay")
    secret_yaml = kubectl(["create", "secret", "generic", "private-cloud-live-test-ca", "-n", "private-cloud",
                           f"--from-file=ca-bundle.crt={ca_bundle}", "--dry-run=client", "-o", "yaml"], capture=True)
    kubectl(["apply", "-f", "-"], input_text=secret_yaml)
    policy = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "private-cloud-live-test-stalwart-relay", "namespace": "private-cloud"},
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "stalwart", "app.kubernetes.io/component": "server"}},
            "policyTypes": ["Egress"],
            "egress": [{"to": [{"ipBlock": {"cidr": f"{host_ip}/32"}}], "ports": [{"protocol": "TCP", "port": port}]}],
        },
    }
    kubectl(["apply", "-f", "-"], input_text=json.dumps(policy))
    patch = {
        "spec": {"template": {"spec": {
            "hostAliases": [{"ip": host_ip, "hostnames": [relay_host]}],
            "volumes": [{"name": "private-cloud-live-test-ca", "secret": {"secretName": "private-cloud-live-test-ca"}}],
            "containers": [{"name": "stalwart", "env": [
                {"name": "SSL_CERT_FILE", "value": "/tmp/private-cloud-live-test/ca-bundle.crt"},
                {"name": "CURL_CA_BUNDLE", "value": "/tmp/private-cloud-live-test/ca-bundle.crt"},
                {"name": "REQUESTS_CA_BUNDLE", "value": "/tmp/private-cloud-live-test/ca-bundle.crt"},
                {"name": "NODE_EXTRA_CA_CERTS", "value": "/tmp/private-cloud-live-test/ca-bundle.crt"},
            ], "volumeMounts": [{"name": "private-cloud-live-test-ca", "mountPath": "/tmp/private-cloud-live-test", "readOnly": True}]}],
        }}}
    }
    kubectl(["patch", "statefulset", "stalwart", "-n", "private-cloud", "--type", "strategic", "-p", json.dumps(patch)])
    kubectl(["rollout", "status", "statefulset/stalwart", "-n", "private-cloud", "--timeout=180s"])


def start_smtp(configuration):
    pid_file = ARTIFACTS / "smtp-relay.pid"
    log_file = ARTIFACTS / "smtp-relay.log"
    if pid_file.exists() and process_running(pid_file):
        return
    log_file.write_text("")
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("live_test.py").resolve()), "smtp-server", "--config", "/tank/secure/backup/private-cloud-config/private-cloud.yml"],
            cwd=Path.cwd(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    pid_file.write_text(str(process.pid) + "\n")
    os.chmod(pid_file, 0o600)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"SMTP mock exited early; inspect {log_file}")
        if port_is_open(int(configuration["private_cloud"]["stalwart"]["relay_port"])):
            return
        time.sleep(0.1)
    raise RuntimeError(f"SMTP mock did not become ready; inspect {log_file}")


def stop_smtp():
    stop_service("smtp-relay.pid")


def start_cloudflare(configuration, config_path):
    url = urlsplit(configuration["private_cloud"]["networking"].get("cloudflare_api_url", ""))
    if url.scheme != "https" or not url.hostname or not url.port:
        raise ValueError("Set networking.cloudflare_api_url to the local HTTPS mock endpoint before starting it")
    pid_file = ARTIFACTS / "cloudflare-mock.pid"
    log_file = ARTIFACTS / "cloudflare-mock.log"
    if pid_file.exists() and process_running(pid_file):
        return
    log_file.write_text("")
    mock = Path(__file__).with_name("cloudflare_mock.py")
    with log_file.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, str(mock), str(config_path.resolve())], cwd=Path.cwd(),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    pid_file.write_text(str(process.pid) + "\n")
    os.chmod(pid_file, 0o600)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Cloudflare API mock exited early; inspect {log_file}")
        if port_is_open(url.port):
            return
        time.sleep(0.1)
    raise RuntimeError(f"Cloudflare API mock did not become ready; inspect {log_file}")


def start_acme(configuration, config_path):
    endpoint = urlsplit(configuration["private_cloud"]["networking"]["acme_directory_url"])
    if not endpoint.port:
        raise ValueError("The ACME trial endpoint needs an explicit port")
    pid_file = ARTIFACTS / "acme-mock.pid"
    if pid_file.exists() and process_running(pid_file):
        return
    with (ARTIFACTS / "acme-mock.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("acme_mock.py")), str(config_path.resolve())], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    pid_file.write_text(str(process.pid) + "\n")
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("The ACME mock exited before accepting connections")
        if port_is_open(endpoint.port):
            return
        time.sleep(0.1)
    raise RuntimeError("The ACME mock did not become ready")


def allow_acme(configuration):
    cloud = configuration["private_cloud"]
    endpoint = urlsplit(cloud["networking"]["acme_directory_url"])
    import socket
    address = socket.gethostbyname(endpoint.hostname)
    for namespace, workload in (("private-cloud", "stalwart"), ("edge", "traefik")):
        policy = {
            "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": "private-cloud-live-test-acme", "namespace": namespace},
            "spec": {
                "podSelector": {"matchLabels": {"app.kubernetes.io/name": workload}},
                "policyTypes": ["Egress"],
                "egress": [{"to": [{"ipBlock": {"cidr": f"{address}/32"}}], "ports": [{"protocol": "TCP", "port": endpoint.port or 443}]}],
            },
        }
        kubectl(["apply", "-f", "-"], input_text=json.dumps(policy))


def stop_service(pid_filename):
    pid_file = ARTIFACTS / pid_filename
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
        except ProcessLookupError:
            pass
        pid_file.unlink(missing_ok=True)


def allow_cloudflare(configuration):
    cloud = configuration["private_cloud"]
    endpoint = urlsplit(cloud["networking"]["cloudflare_api_url"])
    address = cloud["media"]["openvpn"]["endpoint_ip"]
    if endpoint.hostname != cloud["stalwart"]["relay_host"]:
        import socket
        address = socket.gethostbyname(endpoint.hostname)
    policy = {
        "apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "private-cloud-live-test-cloudflare", "namespace": "dns-system"},
        "spec": {
            "podSelector": {"matchLabels": {"app.kubernetes.io/name": "cloudflare-ddns"}},
            "policyTypes": ["Egress"],
            "egress": [{"to": [{"ipBlock": {"cidr": f"{address}/32"}}], "ports": [{"protocol": "TCP", "port": endpoint.port}]}],
        },
    }
    kubectl(["apply", "-f", "-"], input_text=json.dumps(policy))
    patch = {
        "spec": {"jobTemplate": {"spec": {"template": {"spec": {
            "volumes": [{"name": "private-cloud-live-test-ca", "secret": {"secretName": "private-cloud-live-test-ca"}}],
            "containers": [{"name": "updater", "env": [
                {"name": "SSL_CERT_FILE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                {"name": "CURL_CA_BUNDLE", "value": "/etc/ssl/certs/ca-certificates.crt"},
                {"name": "REQUESTS_CA_BUNDLE", "value": "/etc/ssl/certs/ca-certificates.crt"},
            ], "volumeMounts": [{"name": "private-cloud-live-test-ca", "mountPath": "/etc/ssl/certs/ca-certificates.crt", "subPath": "ca-bundle.crt", "readOnly": True}]}],
        }}}}}
    }
    kubectl(["patch", "cronjob", "cloudflare-ddns", "-n", "dns-system", "--type", "strategic", "-p", json.dumps(patch)])


def run_ddns(configuration):
    name = "cloudflare-ddns-live-test"
    kubectl(["delete", "job", name, "-n", "dns-system", "--ignore-not-found=true"])
    kubectl(["create", "job", f"--from=cronjob/cloudflare-ddns", name, "-n", "dns-system"])
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = kubectl_json(["get", "job", name, "-n", "dns-system", "-o", "json"])
        conditions = job.get("status", {}).get("conditions", [])
        if any(item["type"] == "Complete" and item["status"] == "True" for item in conditions):
            break
        if any(item["type"] == "Failed" and item["status"] == "True" for item in conditions):
            output = kubectl(["logs", f"job/{name}", "-n", "dns-system"], capture=True)
            raise RuntimeError(f"Cloudflare DDNS mock job failed: {output.strip()}")
        time.sleep(2)
    else:
        raise RuntimeError("Cloudflare DDNS mock job did not complete within 180 seconds")
    output = kubectl(["logs", f"job/{name}", "-n", "dns-system"], capture=True)
    result = json.loads(output)
    expected = set(configuration["private_cloud"]["networking"]["managed_records"])
    records = json.loads((ARTIFACTS / "cloudflare-records.json").read_text())
    observed = {record["name"] for record in records if record["content"] == result["address"]}
    if not expected.issubset(observed):
        raise RuntimeError("Cloudflare mock does not contain every configured A record")
    print(json.dumps({"job": name, "address": result["address"], "records": len(expected), "updated": len(result["updated"])}, separators=(",", ":")))


async def serve_smtp(configuration):
    cloud = configuration["private_cloud"]
    relay = cloud["stalwart"]
    credentials = json.loads((ARTIFACTS / "mock-credentials.json").read_text())
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(str(ARTIFACTS / "server.crt"), str(ARTIFACTS / "server.key"))
    if relay["relay_implicit_tls"]:
        async def handle(reader, writer, encrypted):
            await smtp_session(reader, writer, tls, credentials, cloud, plaintext=not encrypted)

        await serve_sniffed("0.0.0.0", int(relay["relay_port"]), tls, handle)
        return

    def accept(reader, writer):
        asyncio.create_task(smtp_session(reader, writer, tls, credentials, cloud))

    server = await asyncio.start_server(accept, "0.0.0.0", int(relay["relay_port"]))
    async with server:
        await server.serve_forever()


async def smtp_session(reader, writer, tls, credentials, cloud, plaintext=False):
    authenticated = False
    data_mode = False
    message = []
    sender = ""
    recipients = []
    try:
        await smtp_reply(writer, "220 private-cloud test relay ready")
        while line := await reader.readline():
            command = line.decode(errors="replace").rstrip("\r\n")
            upper = command.upper()
            if data_mode:
                if command == ".":
                    try:
                        await asyncio.to_thread(deliver_message, cloud, sender, recipients, message)
                    except (OSError, RuntimeError, ValueError) as error:
                        await smtp_reply(writer, "451 4.3.0 local delivery failed")
                        print(f"Mock SMTP delivery failed: {type(error).__name__}", file=sys.stderr, flush=True)
                    else:
                        save_message(message)
                        await smtp_reply(writer, "250 2.0.0 delivered by local test relay")
                    message = []
                    recipients = []
                    data_mode = False
                else:
                    message.append(command[1:] if command.startswith("..") else command)
            elif upper.startswith("EHLO") or upper.startswith("HELO"):
                replies = ["250-private-cloud.test", "250-PIPELINING", "250-SIZE 10485760"]
                if not writer.get_extra_info("ssl_object") and not plaintext:
                    replies.append("250-STARTTLS")
                else:
                    replies.append("250-AUTH PLAIN LOGIN")
                replies.append("250 8BITMIME")
                writer.write(("\r\n".join(replies) + "\r\n").encode())
                await writer.drain()
            elif upper == "STARTTLS" and not writer.get_extra_info("ssl_object"):
                await smtp_reply(writer, "220 2.0.0 ready to start TLS")
                await writer.start_tls(tls)
            elif upper.startswith("AUTH PLAIN"):
                token = command.partition(" ")[2].partition(" ")[2].strip()
                if not token:
                    await smtp_reply(writer, "334 ")
                    token = (await reader.readline()).decode().strip()
                authenticated = check_smtp_auth(token, credentials)
                await smtp_reply(writer, "235 2.7.0 authenticated" if authenticated else "535 5.7.8 invalid credentials")
            elif upper == "AUTH LOGIN":
                await smtp_reply(writer, "334 VXNlcm5hbWU6")
                username = decode_base64_line(await reader.readline())
                await smtp_reply(writer, "334 UGFzc3dvcmQ6")
                password = decode_base64_line(await reader.readline())
                authenticated = username == credentials["relay_username"] and password == credentials["relay_password"]
                await smtp_reply(writer, "235 2.7.0 authenticated" if authenticated else "535 5.7.8 invalid credentials")
            elif upper.startswith("MAIL FROM:"):
                if authenticated:
                    sender = envelope_address(command)
                    recipients = []
                await smtp_reply(writer, "250 2.1.0 sender accepted" if authenticated else "530 5.7.0 authenticate first")
            elif upper.startswith("RCPT TO:"):
                if authenticated:
                    recipients.append(envelope_address(command))
                await smtp_reply(writer, "250 2.1.5 recipient accepted" if authenticated else "530 5.7.0 authenticate first")
            elif upper == "DATA":
                if authenticated:
                    data_mode = True
                    await smtp_reply(writer, "354 end with <CRLF>.<CRLF>")
                else:
                    await smtp_reply(writer, "530 5.7.0 authenticate first")
            elif upper in {"NOOP", "RSET"}:
                if upper == "RSET":
                    sender, recipients, message = "", [], []
                await smtp_reply(writer, "250 2.0.0 ok")
            elif upper == "QUIT":
                await smtp_reply(writer, "221 2.0.0 bye")
                return
            else:
                await smtp_reply(writer, "502 5.5.2 command not supported")
    except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
        return
    finally:
        writer.close()
        await writer.wait_closed()


def create_certificates(cloud, endpoint_ip):
    ca_key = ARTIFACTS / "ca.key"
    ca_cert = ARTIFACTS / "ca.crt"
    certificate_files = [ca_key, ca_cert, ARTIFACTS / "server.crt", ARTIFACTS / "server.key",
                         ARTIFACTS / "client.crt", ARTIFACTS / "client.key", ARTIFACTS / "tls-crypt.key"]
    if all(path.is_file() for path in certificate_files):
        return
    if not ca_key.exists() or not ca_cert.exists():
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "14",
             "-keyout", str(ca_key), "-out", str(ca_cert), "-subj", "/CN=Private Cloud Live Test CA",
             "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
        os.chmod(ca_key, 0o600)

    names = configured_hostnames(cloud)
    relay_host = cloud.get("stalwart", {}).get("relay_host")
    if relay_host:
        names.add(relay_host.rstrip("."))
    extensions = [f"DNS.{index} = {name}" for index, name in enumerate(sorted(names), start=1)]
    extensions.append(f"IP.1 = {endpoint_ip}")
    ext_file = ARTIFACTS / "server-cert.ext"
    ext_file.write_text("\n".join([
        "[server_cert]", "basicConstraints=critical,CA:FALSE", "keyUsage=critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage=serverAuth", "subjectAltName=@subject_alt_names", "[subject_alt_names]", *extensions, "",
    ]))
    create_leaf_certificate("server", "serverAuth", ext_file)
    create_leaf_certificate("client", "clientAuth", None)
    os.chmod(ARTIFACTS / "server.key", 0o600)
    os.chmod(ARTIFACTS / "client.key", 0o600)
    run(["openvpn", "--genkey", "secret", str(ARTIFACTS / "tls-crypt.key")])
    os.chmod(ARTIFACTS / "tls-crypt.key", 0o600)


def create_leaf_certificate(name, purpose, extension_file):
    key = ARTIFACTS / f"{name}.key"
    csr = ARTIFACTS / f"{name}.csr"
    certificate = ARTIFACTS / f"{name}.crt"
    run(["openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(csr), "-subj", f"/CN=private-cloud-live-test-{name}"])
    ext = extension_file
    if ext is None:
        ext = ARTIFACTS / f"{name}-cert.ext"
        ext.write_text("\n".join([
            "[client_cert]", "basicConstraints=critical,CA:FALSE", "keyUsage=critical,digitalSignature,keyEncipherment",
            f"extendedKeyUsage={purpose}", "",
        ]))
    run(["openssl", "x509", "-req", "-in", str(csr), "-CA", str(ARTIFACTS / "ca.crt"),
         "-CAkey", str(ARTIFACTS / "ca.key"), "-CAcreateserial", "-out", str(certificate),
         "-days", "14", "-sha256", "-extfile", str(ext), "-extensions", "server_cert" if name == "server" else "client_cert"])


def create_openvpn_files(endpoint_ip, endpoint_port, endpoint_protocol, credentials):
    auth_script = ARTIFACTS / "verify-openvpn-auth.py"
    auth_script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        f"expected = json.loads(pathlib.Path({str(ARTIFACTS / 'mock-credentials.json')!r}).read_text())\n"
        "received = pathlib.Path(sys.argv[1]).read_text().splitlines()\n"
        "sys.exit(0 if received == [expected['openvpn_username'], expected['openvpn_password']] else 1)\n"
    )
    os.chmod(auth_script, 0o700)
    server_config = "\n".join([
        f"local {endpoint_ip}", f"port {endpoint_port}", f"proto {endpoint_protocol}", "dev tun-live-test",
        "topology subnet", "server 10.253.0.0 255.255.255.0", "push \"redirect-gateway def1 bypass-dhcp\"",
        "push \"dhcp-option DNS 1.1.1.1\"", f"ca {ARTIFACTS / 'ca.crt'}", f"cert {ARTIFACTS / 'server.crt'}",
        f"key {ARTIFACTS / 'server.key'}", "dh none", f"tls-crypt {ARTIFACTS / 'tls-crypt.key'}",
        "verify-client-cert require", "username-as-common-name", "script-security 2",
        f"auth-user-pass-verify {auth_script} via-file", "auth SHA256", "data-ciphers AES-256-GCM:AES-128-GCM",
        "keepalive 5 20", "persist-key", "persist-tun", "status /var/lib/private-cloud-live-test/openvpn-status.log",
        "verb 3", "",
    ])
    (ARTIFACTS / "openvpn-server.conf").write_text(server_config)
    os.chmod(ARTIFACTS / "openvpn-server.conf", 0o600)

    client_config = "\n".join([
        "client", "dev tun", f"proto {endpoint_protocol}", f"remote {endpoint_ip} {endpoint_port}",
        "resolv-retry infinite", "nobind", "persist-key", "persist-tun", "remote-cert-tls server",
        "auth-nocache", "auth SHA256", "data-ciphers AES-256-GCM:AES-128-GCM", "verb 3", "auth-user-pass",
        inline_block("ca", ARTIFACTS / "ca.crt"), inline_block("cert", ARTIFACTS / "client.crt"),
        inline_block("key", ARTIFACTS / "client.key"), inline_block("tls-crypt", ARTIFACTS / "tls-crypt.key"), "",
    ])
    profile = ARTIFACTS / "client.ovpn"
    profile.write_text(client_config)
    os.chmod(profile, 0o600)


def read_or_create_credentials(cloud):
    credentials_file = ARTIFACTS / "mock-credentials.json"
    if credentials_file.exists():
        return json.loads(credentials_file.read_text())
    username = cloud.get("stalwart", {}).get("relay_username", "private-cloud-test")
    credentials = {
        "openvpn_username": f"test-{secrets.token_hex(4)}",
        "openvpn_password": secrets.token_urlsafe(24),
        "relay_username": username,
        "relay_password": secrets.token_urlsafe(24),
    }
    credentials_file.write_text(json.dumps(credentials, separators=(",", ":")) + "\n")
    os.chmod(credentials_file, 0o600)
    return credentials


def configured_hostnames(cloud):
    networking = cloud["networking"]
    names = set(networking.get("managed_records", []))
    names.add(networking.get("zabbix_hostname", ""))
    names.add(networking.get("amneziawg", {}).get("hostname", ""))
    for stage in ("media", "onlyoffice", "opencloud", "grist", "affine", "immich", "stalwart", "logging"):
        names.add(cloud.get(stage, {}).get("hostname", ""))
    return {name.rstrip(".") for name in names if name and "." in name}


def write_host_mapping(configuration):
    cloud = configuration["private_cloud"]
    address = cloud["networking"]["traefik_internal_ip"]
    records = configured_hostnames(cloud)
    relay = cloud.get("stalwart", {}).get("relay_host")
    if relay:
        records.add(relay.rstrip("."))
    lines = ["# BEGIN private-cloud-live-test", f"{address} " + " ".join(sorted(records)), "# END private-cloud-live-test"]
    hosts = Path("/etc/hosts")
    current = hosts.read_text()
    start, end = "# BEGIN private-cloud-live-test", "# END private-cloud-live-test"
    if start in current and end in current:
        before, remainder = current.split(start, 1)
        _, after = remainder.split(end, 1)
        current = before.rstrip() + "\n" + after.lstrip("\n")
    hosts.write_text(current.rstrip() + "\n" + "\n".join(lines) + "\n")


def add_vpn_nat():
    route_output = subprocess.run(["ip", "-j", "route", "show", "default"], check=True, capture_output=True, text=True)
    routes = json.loads(route_output.stdout)
    interface = routes[0]["dev"]
    table = "\n".join([
        "table ip private_cloud_live_test {",
        "  chain postrouting {",
        "    type nat hook postrouting priority srcnat; policy accept;",
        f'    oifname "{interface}" ip saddr {VPN_NETWORK} masquerade',
        "  }", "}", "",
    ])
    subprocess.run(["nft", "delete", "table", "ip", "private_cloud_live_test"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["nft", "-f", "-"], input=table, text=True, check=True)


def kubectl(arguments, capture=False, input_text=None):
    command = ["k0s", "kubectl", *arguments]
    result = subprocess.run(command, check=True, input=input_text, text=True, capture_output=capture)
    return result.stdout if capture else None


def kubectl_json(arguments):
    result = kubectl(arguments, capture=True)
    return json.loads(result)


def save_original(filename, value):
    path = ARTIFACTS / filename
    if not path.exists():
        path.write_text(json.dumps(value, separators=(",", ":")) + "\n")
        os.chmod(path, 0o600)


def insert_hosts_plugin(corefile, block):
    marker = "# BEGIN private-cloud-live-test DNS"
    if marker in corefile:
        return corefile
    lines = corefile.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == ".:53 {":
            lines[index + 1:index + 1] = ["  " + part if part else "" for part in block.rstrip().splitlines()]
            return "\n".join(lines) + "\n"
    raise RuntimeError("Could not find the CoreDNS root zone in Corefile")


def remove_marked_block(contents, begin, end):
    if begin not in contents:
        return contents
    start = contents.index(begin)
    finish = contents.index(end, start) + len(end)
    return contents[:start].rstrip() + "\n" + contents[finish:].lstrip("\n")


def restart_coredns(namespace):
    deployments = kubectl_json(["get", "deployments", "-n", namespace, "-o", "json"])
    names = [item["metadata"]["name"] for item in deployments["items"] if "coredns" in item["metadata"]["name"]]
    if not names:
        raise RuntimeError("Could not find a CoreDNS deployment to restart")
    for name in names:
        kubectl(["rollout", "restart", f"deployment/{name}", "-n", namespace])
        kubectl(["rollout", "status", f"deployment/{name}", "-n", namespace, "--timeout=180s"])


async def smtp_reply(writer, message):
    writer.write((message + "\r\n").encode())
    await writer.drain()


def check_smtp_auth(token, credentials):
    try:
        decoded = base64.b64decode(token, validate=True).decode()
        _, username, password = decoded.split("\x00", 2)
        return username == credentials["relay_username"] and password == credentials["relay_password"]
    except (ValueError, UnicodeDecodeError):
        return False


def decode_base64_line(line):
    try:
        return base64.b64decode(line.strip(), validate=True).decode()
    except (ValueError, UnicodeDecodeError):
        return ""


def save_message(lines):
    mailbox = ARTIFACTS / "smtp-relay-deliveries"
    mailbox.mkdir(mode=0o700, exist_ok=True)
    message = "\n".join(lines).encode() + b"\n"
    destination = mailbox / f"{int(time.time())}-{uuid.uuid4().hex}.eml"
    destination.write_bytes(message)
    os.chmod(destination, 0o600)


def port_is_open(port):
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def process_running(pid_file):
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
        return True
    except (ValueError, OSError):
        return False


def inline_block(name, path):
    return f"<{name}>\n{path.read_text().strip()}\n</{name}>"


def read_configuration(path):
    with path.open() as stream:
        configuration = yaml.safe_load(stream)
    if not isinstance(configuration, dict) or not isinstance(configuration.get("private_cloud"), dict):
        raise ValueError("Configuration file does not contain private_cloud")
    return configuration


def run(command):
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
