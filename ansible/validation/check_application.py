#!/usr/bin/env python3
"""Validate a private-cluster HTTP service through the Kubernetes API tunnel."""

import json
import sys

from application_helpers import validate_http_application


def main():
    config = json.load(sys.stdin)
    result = validate_http_application(config)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
