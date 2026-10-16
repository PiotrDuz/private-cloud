"""Helpers that compare live host and cluster state with repository-managed resources."""

import json
import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
MANAGED_NAMESPACES = ["private-cloud", "media", "edge", "network-access", "dns-system", "observability"]
TRUST_ENVIRONMENT = {"SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "GRPC_DEFAULT_SSL_ROOTS_FILE_PATH", "LEGO_CA_CERTIFICATES"}
TRUST_PATHS = ("/etc/ssl", "/etc/pki", "/usr/local/share/ca-certificates", "/etc/ca-certificates")


def kubectl_items(kind, namespace=None, name=None):
    if name:
        return [json.loads(kubectl(["get", kind, name, "-n", namespace, "-o", "json"]))]
    items = json.loads(kubectl(["get", kind, "--all-namespaces", "-o", "json"]))["items"]
    return [item for item in items if item["metadata"]["namespace"] in MANAGED_NAMESPACES]


def workload_overrides(kind, workloads):
    findings = []
    for workload in workloads:
        label = f"{kind[:-1]} {workload['metadata']['namespace']}/{workload['metadata']['name']}"
        spec = workload["spec"]["jobTemplate"]["spec"]["template"]["spec"] if kind == "cronjobs" else workload["spec"]["template"]["spec"]
        if spec.get("hostAliases"):
            findings.append(f"{label} pins hostnames with hostAliases")
        for container in spec.get("initContainers", []) + spec.get("containers", []):
            overridden = sorted(TRUST_ENVIRONMENT & {entry["name"] for entry in container.get("env", [])})
            if overridden:
                findings.append(f"{label} overrides TLS trust with {', '.join(overridden)}")
            mounted = [mount["mountPath"] for mount in container.get("volumeMounts", []) if mount["mountPath"].startswith(TRUST_PATHS)]
            if mounted:
                findings.append(f"{label} mounts trust stores at {', '.join(mounted)}")
    return findings


def local_trust_anchors():
    return [str(path) for path in sorted(Path("/usr/local/share/ca-certificates").rglob("*")) if path.is_file()]


def hosts_overrides(hostnames):
    wanted = {name.rstrip(".").lower() for name in hostnames if name}
    found = set()
    for line in Path("/etc/hosts").read_text().splitlines():
        fields = line.split("#", 1)[0].split()
        found.update(name.lower() for name in fields[1:] if name.lower() in wanted)
    return sorted(found)


def kubectl(arguments):
    return subprocess.run(["k0s", "kubectl", *arguments], check=True, capture_output=True, text=True).stdout
