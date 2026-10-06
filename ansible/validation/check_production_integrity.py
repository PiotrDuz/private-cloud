#!/usr/bin/env python3
"""Reject trust, DNS, routing, and policy overrides that the repository does not install."""

import json
import sys

from integrity_helpers import (
    MANAGED_NAMESPACES, kubectl_items, local_trust_anchors, repository_network_policies,
    hosts_overrides, workload_overrides,
)


def main():
    config = json.load(sys.stdin)
    findings = []
    findings += [f"local trust anchor {path}" for path in local_trust_anchors()]
    findings += [f"/etc/hosts override for {name}" for name in hosts_overrides(config["hostnames"])]
    expected_policies = repository_network_policies()
    for policy in kubectl_items("networkpolicies"):
        if policy["metadata"]["name"] not in expected_policies:
            findings.append(f"unmanaged NetworkPolicy {policy['metadata']['namespace']}/{policy['metadata']['name']}")
    for secret in kubectl_items("secrets"):
        if secret.get("type") == "kubernetes.io/tls":
            findings.append(f"unmanaged TLS Secret {secret['metadata']['namespace']}/{secret['metadata']['name']}")
    for kind in ("deployments", "statefulsets", "daemonsets", "cronjobs"):
        findings += workload_overrides(kind, kubectl_items(kind))
    corefile = kubectl_items("configmaps", "kube-system", "coredns")[0]["data"]["Corefile"]
    if any(line.strip().split(" ")[0] in {"hosts", "rewrite", "template", "file"} for line in corefile.splitlines()):
        findings.append("cluster CoreDNS contains static host overrides")
    dynamic = kubectl_items("configmaps", "edge", "traefik-dynamic")[0]["data"]["tcp.yaml"]
    if any(line.strip() in {"tls:", "certificates:"} for line in dynamic.splitlines()):
        findings.append("Traefik dynamic configuration injects certificates")
    if findings:
        raise RuntimeError("Production integrity check failed: " + "; ".join(findings))
    print(json.dumps({"namespaces": MANAGED_NAMESPACES, "network_policies": len(expected_policies), "overrides": 0}, separators=(",", ":")))


if __name__ == "__main__":
    main()
