#!/usr/bin/env python3
"""Reject trust, DNS, routing, and policy overrides that the repository does not install."""

import json
import sys

import yaml

from integrity_helpers import MANAGED_NAMESPACES, kubectl_items, local_trust_anchors, hosts_overrides, workload_overrides
from network_policy_helpers import policy_findings


def main():
    config = json.load(sys.stdin)
    findings = []
    findings += [f"local trust anchor {path}" for path in local_trust_anchors()]
    findings += [f"/etc/hosts override for {name}" for name in hosts_overrides(config["hostnames"])]
    policy_problems, policy_count = policy_findings(config, kubectl_items("networkpolicies"))
    findings += policy_problems
    for secret in kubectl_items("secrets"):
        if secret.get("type") == "kubernetes.io/tls":
            findings.append(f"unmanaged TLS Secret {secret['metadata']['namespace']}/{secret['metadata']['name']}")
    for kind in ("deployments", "statefulsets", "daemonsets", "cronjobs"):
        findings += workload_overrides(kind, kubectl_items(kind))
    corefile = kubectl_items("configmaps", "kube-system", "coredns")[0]["data"]["Corefile"]
    if any(line.strip().split(" ")[0] in {"hosts", "rewrite", "template", "file"} for line in corefile.splitlines()):
        findings.append("cluster CoreDNS contains static host overrides")
    for configmap in kubectl_items("configmaps"):
        if configmap["metadata"]["namespace"] == "edge" and (configmap["metadata"]["name"] == "traefik-dynamic" or configmap["metadata"].get("labels", {}).get("private-cloud.example/traefik-route") == "true"):
            if any((yaml.safe_load(document) or {}).get("tls") for document in configmap["data"].values()):
                findings.append(f"Traefik configuration {configmap['metadata']['name']} injects certificates")
    if findings:
        raise RuntimeError("Production integrity check failed: " + "; ".join(findings))
    print(json.dumps({"namespaces": MANAGED_NAMESPACES, "network_policies": policy_count, "overrides": 0}, separators=(",", ":")))


if __name__ == "__main__":
    main()
