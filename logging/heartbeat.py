#!/usr/bin/env python3
"""Emit one timestamped host-to-Loki heartbeat."""
import datetime
import json


def main():
    print(json.dumps({"level": "info", "event": "log_pipeline_heartbeat", "time": datetime.datetime.now(datetime.timezone.utc).isoformat()}))


if __name__ == "__main__":
    main()
