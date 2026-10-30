#!/usr/bin/env python3
"""Collect CPU, memory, and container restarts per Kubernetes workload for Zabbix Agent 2."""

import json
import ssl
import sys
import time
import urllib.request
from pathlib import Path

from collector_logging import log_collector_errors


SUFFIXES = {
    "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12,
    "Ki": 1024.0, "Mi": 1024.0 ** 2, "Gi": 1024.0 ** 3, "Ti": 1024.0 ** 4,
}


def main():
    try:
        collector = Collector(json.loads(Path(sys.argv[1]).read_text()))
        result = collector.collect()
    except Exception as error:
        log_collector_errors("kubernetes", [f"collector failed: {error}"])
        raise
    log_collector_errors("kubernetes", result["errors"])
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


def quantity(text):
    number = text.rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return float(number) * SUFFIXES[text[len(number):]]


def workload_name(pod):
    """Name a pod by its controller; Job pods are transient and skipped."""
    metadata = pod["metadata"]
    owners = [owner for owner in metadata.get("ownerReferences", []) if owner.get("controller")]
    if not owners:
        return metadata["name"]
    owner = owners[0]
    if owner["kind"] == "Job":
        return None
    template_hash = metadata.get("labels", {}).get("pod-template-hash")
    if owner["kind"] == "ReplicaSet" and template_hash:
        return owner["name"].removesuffix("-" + template_hash)
    return owner["name"]


class Collector:
    def __init__(self, config):
        self.server = config["server"].rstrip("/")
        self.token = config["token"]
        self.context = ssl.create_default_context(cadata=config["ca"])
        self.errors = []

    def collect(self):
        workloads = {}
        pods = {}
        for pod in self.get("/api/v1/pods")["items"]:
            name = workload_name(pod)
            if name is None or pod["status"].get("phase") in ("Succeeded", "Failed"):
                continue
            namespace = pod["metadata"]["namespace"]
            entry = workloads.setdefault((namespace, name), {"namespace": namespace, "name": name, "cpu": 0.0, "memory": 0, "restarts": 0})
            statuses = pod["status"].get("initContainerStatuses", []) + pod["status"].get("containerStatuses", [])
            entry["restarts"] += sum(status.get("restartCount", 0) for status in statuses)
            pods[(namespace, pod["metadata"]["name"])] = entry
        for usage in self.usage():
            entry = pods.get((usage["metadata"]["namespace"], usage["metadata"]["name"]))
            if entry is None:
                continue
            for container in usage["containers"]:
                entry["cpu"] += quantity(container["usage"]["cpu"])
                entry["memory"] += int(quantity(container["usage"]["memory"]))
        for entry in workloads.values():
            entry["cpu"] = round(entry["cpu"], 4)
        return {
            "generated_at": int(time.time()),
            "workloads": sorted(workloads.values(), key=lambda entry: (entry["namespace"], entry["name"])),
            "error_count": len(self.errors),
            "errors": self.errors,
        }

    def usage(self):
        try:
            return self.get("/apis/metrics.k8s.io/v1beta1/pods")["items"]
        except Exception as error:
            self.errors.append(f"cannot read pod metrics: {error}")
            return []

    def get(self, path):
        request = urllib.request.Request(self.server + path, headers={"Authorization": "Bearer " + self.token, "Accept": "application/json"})
        with urllib.request.urlopen(request, context=self.context, timeout=10) as response:
            return json.load(response)


if __name__ == "__main__":
    main()
