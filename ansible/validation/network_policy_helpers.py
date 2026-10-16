"""Render repository NetworkPolicies and compare their normalized specifications with live ones."""

import ipaddress
import json
import re
from pathlib import Path

import jinja2
import yaml

from integrity_helpers import MANAGED_NAMESPACES, REPOSITORY

SERVICE_STAGES = {
    "affine": "affine", "alloy": "logging", "arr": "media", "bleve": "bleve", "grist": "grist", "immich": "immich",
    "intel-gpu": "intel_gpu", "jellyfin": "media", "manticore": "manticore", "meilisearch": "meilisearch",
    "networking": "networking", "onlyoffice": "onlyoffice", "opencloud": "opencloud", "openobserve": "logging",
    "postgres": "postgres", "redis-affine": "redis_affine", "stalwart": "stalwart", "tika": "tika", "zabbix": "zabbix_server",
}
TAG = re.compile(r"\{%-?\s*(end)?(\w+).*?-?%\}")
OPENERS = {"if", "for", "macro", "call", "filter", "with", "block"}
BRANCHES = {"elif", "else"}


def rendered_network_policies(config):
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    environment.filters["bool"] = lambda value: value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "on"}
    context = {
        "private_cloud": config["private_cloud"],
        "private_cloud_alert_smtp_host": config["alert_smtp_host"],
        "private_cloud_alert_smtp_port": config["alert_smtp_port"],
    }
    policies = {}
    for template in sorted(REPOSITORY.glob("k0s-services/*/templates/*.yaml.j2")):
        for chunk in template_chunks(template.read_text()):
            if not re.search(r"(?m)^\s*kind:\s*NetworkPolicy\s*$", chunk):
                continue
            service = template.parent.parent.name
            if service not in SERVICE_STAGES:
                raise RuntimeError(f"{service} has NetworkPolicies but no stage mapping")
            if not config["private_cloud"]["stages"][SERVICE_STAGES[service]]:
                continue
            for document in yaml.safe_load_all(environment.from_string(chunk).render(context)):
                if document and document.get("kind") == "NetworkPolicy":
                    policies[(document["metadata"]["namespace"], document["metadata"]["name"])] = document
    return policies


def template_chunks(source):
    """Split at document separators and re-wrap each piece in the Jinja blocks that enclose it."""
    chunks, current, stack, start = [], [], [], []
    for line in source.splitlines(keepends=True):
        if re.fullmatch(r"---\s*", line):
            chunks.append(wrap(start, current, stack))
            current, start = [], [list(entry) for entry in stack]
            continue
        current.append(line)
        for tag in TAG.finditer(line):
            closing, keyword = tag.groups()
            if closing and keyword in OPENERS:
                stack.pop()
            elif keyword in OPENERS and not closing:
                stack.append([tag.group(0)])
            elif keyword in BRANCHES:
                stack[-1].append(tag.group(0))
    chunks.append(wrap(start, current, []))
    return chunks


def wrap(start, lines, end_stack):
    return "".join(tag for entry in start for tag in entry) + "".join(lines) + ("\n---\n" if end_stack else "") + "".join(end_for(entry) for entry in reversed(end_stack))


def end_for(entry):
    return "{% end" + re.match(r"\{%-?\s*(\w+)", entry[0]).group(1) + " %}"


def policy_findings(config, live_policies):
    expected = rendered_network_policies(config)
    live = {(policy["metadata"]["namespace"], policy["metadata"]["name"]): policy for policy in live_policies}
    findings = [f"unmanaged NetworkPolicy {namespace}/{name}" for namespace, name in sorted(set(live) - set(expected))]
    findings += [f"missing NetworkPolicy {namespace}/{name}" for namespace, name in sorted(set(expected) - set(live))]
    for key in sorted(set(expected) & set(live)):
        if normalize_spec(expected[key]["spec"]) != normalize_spec(live[key]["spec"]):
            findings.append(f"NetworkPolicy {key[0]}/{key[1]} differs from its rendered specification")
    for namespace in MANAGED_NAMESPACES:
        policy = live.get((namespace, "default-deny"))
        if not policy or normalize_spec(policy["spec"]) != normalize_spec({"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}):
            findings.append(f"namespace {namespace} lacks a default-deny NetworkPolicy for ingress and egress")
    return findings, len(expected)


def normalize_spec(spec):
    egress = spec.get("egress") or []
    ingress = spec.get("ingress") or []
    policy_types = spec.get("policyTypes") or (["Ingress"] + (["Egress"] if egress else []))
    return {
        "podSelector": normalize_selector(spec.get("podSelector")),
        "policyTypes": sorted(policy_types),
        "ingress": sorted(canonical(normalize_rule(rule, "from")) for rule in ingress),
        "egress": sorted(canonical(normalize_rule(rule, "to")) for rule in egress),
    }


def normalize_rule(rule, direction):
    peers = rule.get(direction)
    ports = rule.get("ports")
    return {
        direction: None if peers is None else sorted(canonical(normalize_peer(peer)) for peer in peers),
        "ports": None if ports is None else sorted(canonical(normalize_port(port)) for port in ports),
    }


def normalize_peer(peer):
    result = {}
    if "podSelector" in peer:
        result["podSelector"] = normalize_selector(peer["podSelector"])
    if "namespaceSelector" in peer:
        result["namespaceSelector"] = normalize_selector(peer["namespaceSelector"])
    if "ipBlock" in peer:
        block = peer["ipBlock"]
        result["ipBlock"] = {
            "cidr": str(ipaddress.ip_network(block["cidr"], strict=False)),
            "except": sorted(str(ipaddress.ip_network(cidr, strict=False)) for cidr in block.get("except") or []),
        }
    return result


def normalize_port(port):
    result = {"protocol": port.get("protocol") or "TCP"}
    for key in ("port", "endPort"):
        if port.get(key) is not None:
            result[key] = int(port[key]) if str(port[key]).isdigit() else port[key]
    return result


def normalize_selector(selector):
    selector = selector or {}
    return {
        "matchLabels": dict(sorted((selector.get("matchLabels") or {}).items())),
        "matchExpressions": sorted(
            (canonical({**expression, "values": sorted(expression.get("values") or [])}) for expression in selector.get("matchExpressions") or []),
        ),
    }


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
