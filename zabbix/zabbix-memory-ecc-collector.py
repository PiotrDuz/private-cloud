#!/usr/bin/env python3
"""Collect read-only Linux EDAC memory error counters for Zabbix Agent 2."""

import json
import re
import time
from pathlib import Path


EDAC_ROOT = Path("/sys/devices/system/edac/mc")


def main():
    collector = Collector(EDAC_ROOT)
    print(json.dumps(collector.collect(), separators=(",", ":"), sort_keys=True))


def numeric_suffix(path):
    match = re.search(r"(\d+)$", path.name)
    return int(match.group(1)) if match else -1


class Collector:
    def __init__(self, root):
        self.root = root
        self.errors = []

    def collect(self):
        controllers = {}
        dimms = {}
        for path in self.controller_paths():
            controller = self.controller(path)
            controllers[controller["id"]] = controller
            dimms.update(self.dimms(path, controller["id"]))

        return {
            "generated_at": int(time.time()),
            "available": int(bool(controllers)),
            "corrected_errors": sum(
                controller["corrected_errors"] for controller in controllers.values()
            ),
            "uncorrected_errors": sum(
                controller["uncorrected_errors"] for controller in controllers.values()
            ),
            "controllers": controllers,
            "dimms": dimms,
            "error_count": len(self.errors),
            "errors": self.errors,
        }

    def controller_paths(self):
        try:
            paths = [
                path
                for path in self.root.iterdir()
                if path.is_dir() and re.fullmatch(r"mc\d+", path.name)
            ]
        except FileNotFoundError:
            return []
        except OSError as error:
            self.errors.append(f"cannot read {self.root}: {error}")
            return []
        return sorted(paths, key=numeric_suffix)

    def controller(self, path):
        controller_id = path.name
        return {
            "id": controller_id,
            "name": self.read_text(path / "mc_name", controller_id),
            "corrected_errors": self.read_int(path / "ce_count"),
            "uncorrected_errors": self.read_int(path / "ue_count"),
            "corrected_errors_without_dimm": self.read_int(
                path / "ce_noinfo_count", required=False
            ),
            "uncorrected_errors_without_dimm": self.read_int(
                path / "ue_noinfo_count", required=False
            ),
            "managed_bytes": self.read_int(path / "size_mb", required=False)
            * 1024
            * 1024,
            "seconds_since_reset": self.read_int(
                path / "seconds_since_reset", required=False
            ),
        }

    def dimms(self, controller_path, controller_id):
        paths = []
        for pattern in ("dimm*", "rank*"):
            paths.extend(
                path
                for path in controller_path.glob(pattern)
                if path.is_dir() and re.fullmatch(r"(?:dimm|rank)\d+", path.name)
            )

        dimms = {}
        paths.sort(key=lambda item: (item.name[:4], numeric_suffix(item)))
        for path in paths:
            dimm_id = f"{controller_id}:{path.name}"
            dimms[dimm_id] = {
                "id": dimm_id,
                "controller": controller_id,
                "label": self.read_text(path / "dimm_label", path.name),
                "location": self.read_text(path / "dimm_location", "unknown"),
                "corrected_errors": self.read_int(
                    path / "dimm_ce_count", required=False
                ),
                "uncorrected_errors": self.read_int(
                    path / "dimm_ue_count", required=False
                ),
            }
        return dimms

    def read_text(self, path, default, required=True):
        try:
            value = path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            if required:
                self.errors.append(f"missing EDAC attribute: {path}")
            return default
        except OSError as error:
            self.errors.append(f"cannot read {path}: {error}")
            return default
        return value or default

    def read_int(self, path, required=True):
        value = self.read_text(path, "0", required=required)
        try:
            return int(value)
        except ValueError:
            self.errors.append(f"invalid EDAC counter in {path}: {value!r}")
            return 0


if __name__ == "__main__":
    main()
