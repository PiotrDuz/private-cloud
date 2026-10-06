"""Helpers that compare live host and cluster state with repository-managed resources."""

import json
import re
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


def repository_network_policies():
    names = set()
    for template in sorted(REPOSITORY.glob("k0s-services/*/templates/*.yaml.j2")):
        for document in re.split(r"(?m)^---\s*$", template.read_text()):
            if not re.search(r"(?m)^kind:\s*NetworkPolicy\s*$", document):
                continue
            match = re.search(r"(?m)^metadata:\s*(?:\{\s*name:\s*|\n\s+name:\s*)([A-Za-z0-9.-]+)", document)
            if not match:
                raise RuntimeError(f"{template} contains a NetworkPolicy without a literal name")
            names.add(match.group(1))
    return names


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
