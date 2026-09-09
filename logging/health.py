#!/usr/bin/env python3
"""Read logging health and peer certificates for Zabbix Agent 2."""
import concurrent.futures
import json
import sys
from pathlib import Path
from health_helpers import certificate_health, collect_pipeline


def main():
    config = json.loads(Path(sys.argv[1]).read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        pipeline = executor.submit(collect_pipeline, config)
        certificates = {entry["name"]: executor.submit(certificate_health, config["address"], entry) for entry in config["certificates"]}
        result = pipeline.result()
        result["certificates"] = {name: future.result() for name, future in certificates.items()}
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
