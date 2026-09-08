#!/usr/bin/env python3
"""Bound closed Jellyfin FFmpeg diagnostics by age and total size."""
import json
from pathlib import Path
from log_retention_helpers import prune_diagnostics


def main():
    result = prune_diagnostics(Path("/tank/secure/backup/k0s/services/jellyfin/log"), 7 * 86400, 1024 ** 3)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
