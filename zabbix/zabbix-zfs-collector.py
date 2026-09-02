#!/usr/bin/env python3
"""Collect read-only OpenZFS metrics for Zabbix Agent 2."""

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from email.utils import parsedate_to_datetime


def command_path(name):
    path = shutil.which(name)
    if path:
        return path
    for directory in ("/usr/sbin", "/sbin", "/usr/bin", "/bin"):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return name


ZFS = command_path("zfs")
ZPOOL = command_path("zpool")
POOL_NAME = "tank"
SECURE_DATASET = "tank/secure"
LEAF_DATASETS = (
    "tank/secure/backup/k0s/config",
    "tank/secure/no-backup/k0s/images",
    "tank/secure/no-backup/k0s/ephemeral",
    "tank/secure/backup/k0s/services/postgres",
    "tank/secure/backup/k0s/services/meilisearch",
    "tank/secure/backup/k0s/services/tika",
    "tank/secure/backup/k0s/services/bleve",
    "tank/secure/backup/k0s/services/onlyoffice",
    "tank/secure/backup/k0s/services/opencloud",
    "tank/secure/backup/k0s/services/grist",
    "tank/secure/backup/k0s/services/affine",
    "tank/secure/backup/k0s/services/stalwart",
    "tank/secure/backup/k0s/services/zabbix",
)


class Collector:
    def __init__(self):
        self.errors = []

    def run(self, command):
        env = os.environ.copy()
        env["LC_ALL"] = "C"
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self.errors.append(f"{command[0]} failed: {error}")
            return ""

        if result.returncode != 0:
            detail = result.stderr.strip() or f"exit status {result.returncode}"
            self.errors.append(f"{command[0]} failed: {detail}")
            return ""
        return result.stdout

    @staticmethod
    def number(value):
        value = value.strip()
        if value in ("", "-"):
            return None
        value = value.removesuffix("%").removesuffix("x")
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None

    @staticmethod
    def human_size(value):
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMGTPE]?)(?:i?B)?", value)
        if not match:
            return None
        powers = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}
        return int(float(match.group(1)) * (1024 ** powers[match.group(2)]))

    def pools(self):
        properties = (
            "name,size,allocated,free,fragmentation,capacity,dedupratio,health"
        )
        output = self.run(
            [ZPOOL, "list", "-H", "-p", "-o", properties, POOL_NAME]
        )
        pools = {}
        for line in output.splitlines():
            fields = line.split("\t")
            if len(fields) != 8:
                continue
            name = fields[0]
            pools[name] = {
                "name": name,
                "size": self.number(fields[1]),
                "allocated": self.number(fields[2]),
                "free": self.number(fields[3]),
                "fragmentation": self.number(fields[4]),
                "capacity": self.number(fields[5]),
                "dedup_ratio": self.number(fields[6]),
                "health": fields[7],
                "online": 1 if fields[7] == "ONLINE" else 0,
                "read_errors": 0,
                "write_errors": 0,
                "checksum_errors": 0,
                "permanent_errors": 0,
                "scrub_active": 0,
                "resilver_active": 0,
                "last_scrub_repaired": None,
                "last_scrub_epoch": None,
                "last_scrub_age": None,
                "last_scrub_duration": None,
                "last_scrub_errors": None,
                "autotrim": self.pool_autotrim(name),
                "scan": "none requested",
            }
            pools[name].update(self.pool_io(name))
        return pools

    def pool_autotrim(self, pool):
        output = self.run([ZPOOL, "get", "-H", "-o", "value", "autotrim", pool])
        return 1 if output.strip() == "on" else 0

    def parse_kstat(self, path, required=False):
        values = {}
        try:
            with open(path, encoding="ascii") as handle:
                for line in handle:
                    fields = line.split()
                    if len(fields) < 3:
                        continue
                    try:
                        values[fields[0]] = int(fields[2])
                    except ValueError:
                        continue
        except OSError as error:
            if required:
                self.errors.append(f"cannot read {path}: {error}")
            return {}
        return values

    def pool_io(self, pool):
        path = f"/proc/spl/kstat/zfs/{pool}/iostats"
        stats = self.parse_kstat(path, required=True)
        if not stats:
            return {
                "read_operations": 0,
                "write_operations": 0,
                "read_bytes": 0,
                "write_bytes": 0,
            }

        # OpenZFS 2.4 split ARC and direct I/O counters; older releases expose
        # one aggregate set. Support both layouts without double-counting.
        if "reads" in stats:
            read_operations = stats["reads"]
            write_operations = stats.get("writes", 0)
            read_bytes = stats.get("nread", 0)
            write_bytes = stats.get("nwritten", 0)
        else:
            read_operations = stats.get("arc_read_count", 0) + stats.get(
                "direct_read_count", 0
            )
            write_operations = stats.get("arc_write_count", 0) + stats.get(
                "direct_write_count", 0
            )
            read_bytes = stats.get("arc_read_bytes", 0) + stats.get(
                "direct_read_bytes", 0
            )
            write_bytes = stats.get("arc_write_bytes", 0) + stats.get(
                "direct_write_bytes", 0
            )
        return {
            "read_operations": read_operations,
            "write_operations": write_operations,
            "read_bytes": read_bytes,
            "write_bytes": write_bytes,
        }

    def status(self, pools):
        output = self.run([ZPOOL, "status", "-P", "-p", POOL_NAME])
        vdevs = {}
        current_pool = None
        in_config = False

        for raw_line in output.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("pool:"):
                current_pool = stripped.split(":", 1)[1].strip()
                in_config = False
                continue
            if current_pool is None or current_pool not in pools:
                continue
            if stripped.startswith("scan:"):
                scan = stripped.split(":", 1)[1].strip()
                pools[current_pool]["scan"] = scan
                pools[current_pool]["scrub_active"] = int("scrub in progress" in scan)
                pools[current_pool]["resilver_active"] = int("resilver in progress" in scan)
                repaired = re.search(r"scrub repaired (\S+)", scan)
                if repaired:
                    pools[current_pool]["last_scrub_repaired"] = self.human_size(
                        repaired.group(1)
                    )
                scrub_errors = re.search(r"with ([0-9]+) errors?", scan)
                if scrub_errors:
                    pools[current_pool]["last_scrub_errors"] = int(
                        scrub_errors.group(1)
                    )
                duration = re.search(r" in ([0-9]+):([0-9]+):([0-9]+)", scan)
                if duration:
                    hours, minutes, seconds = map(int, duration.groups())
                    pools[current_pool]["last_scrub_duration"] = (
                        hours * 3600 + minutes * 60 + seconds
                    )
                if scan.startswith("scrub repaired") and " on " in scan:
                    date_text = scan.rsplit(" on ", 1)[1]
                    try:
                        parsed = parsedate_to_datetime(date_text)
                        if parsed.tzinfo is None:
                            parsed = parsed.astimezone()
                        pools[current_pool]["last_scrub_epoch"] = int(parsed.timestamp())
                    except (TypeError, ValueError, OverflowError):
                        pass
                continue
            if stripped == "config:":
                in_config = True
                continue
            if stripped.startswith("errors:"):
                pools[current_pool]["permanent_errors"] = int(
                    "No known data errors" not in stripped
                )
                in_config = False
                continue
            if not in_config:
                continue

            fields = stripped.split()
            if len(fields) < 5 or not all(value.isdigit() for value in fields[-3:]):
                continue
            name, state = fields[0], fields[1]
            read_errors, write_errors, checksum_errors = map(int, fields[-3:])
            if name == current_pool:
                pools[current_pool]["read_errors"] = read_errors
                pools[current_pool]["write_errors"] = write_errors
                pools[current_pool]["checksum_errors"] = checksum_errors
            elif name.startswith("/"):
                vdev_id = f"{current_pool}:{name}"
                vdevs[vdev_id] = {
                    "id": vdev_id,
                    "pool": current_pool,
                    "name": name,
                    "state": state,
                    "online": 1 if state == "ONLINE" else 0,
                    "read_errors": read_errors,
                    "write_errors": write_errors,
                    "checksum_errors": checksum_errors,
                }
        return vdevs

    def datasets(self):
        datasets = {}
        for name in LEAF_DATASETS:
            output = self.run(
                [
                    ZFS,
                    "list",
                    "-H",
                    "-p",
                    "-o",
                    "name,used,quota",
                    name,
                ]
            )
            fields = output.strip().split("\t")
            if len(fields) != 3:
                continue
            used = self.number(fields[1])
            quota = self.number(fields[2])
            if not isinstance(used, int):
                self.errors.append(f"{name} returned invalid used space")
                continue
            if not isinstance(quota, int) or quota <= 0:
                self.errors.append(f"{name} has no positive quota")
                continue
            datasets[name] = {
                "name": name,
                "used": used,
                "quota": quota,
                "utilization": round(used * 100 / quota, 4),
            }
        return datasets

    def secure_dataset(self):
        output = self.run(
            [
                ZFS,
                "list",
                "-H",
                "-o",
                "name,mounted,encryption,keystatus",
                SECURE_DATASET,
            ]
        )
        fields = output.strip().split("\t")
        if len(fields) != 4:
            return {
                "name": SECURE_DATASET,
                "mounted": 0,
                "encrypted": 0,
                "key_available": 0,
            }
        return {
            "name": fields[0],
            "mounted": 1 if fields[1] == "yes" else 0,
            "encrypted": 0 if fields[2] in ("off", "-") else 1,
            "key_available": 1 if fields[3] == "available" else 0,
        }

    def arc(self):
        stats = self.parse_kstat("/proc/spl/kstat/zfs/arcstats", required=True)
        hits = stats.get("hits", 0)
        misses = stats.get("misses", 0)
        total = hits + misses
        l2_hits = stats.get("l2_hits", 0)
        l2_misses = stats.get("l2_misses", 0)
        l2_total = l2_hits + l2_misses
        return {
            "size": stats.get("size", 0),
            "target_size": stats.get("c", 0),
            "minimum_size": stats.get("c_min", 0),
            "maximum_size": stats.get("c_max", 0),
            "metadata_used": stats.get("arc_meta_used", stats.get("metadata_size", 0)),
            "metadata_limit": stats.get("arc_meta_limit", stats.get("meta", 0)),
            "hits": hits,
            "misses": misses,
            "hit_ratio": round(hits * 100 / total, 4) if total else 0,
            "l2_size": stats.get("l2_size", 0),
            "l2_hits": l2_hits,
            "l2_misses": l2_misses,
            "l2_hit_ratio": round(l2_hits * 100 / l2_total, 4) if l2_total else 0,
            "l2_read_bytes": stats.get("l2_read_bytes", 0),
            "l2_write_bytes": stats.get("l2_write_bytes", 0),
            "l2_io_errors": stats.get("l2_io_error", 0),
            "l2_checksum_errors": stats.get("l2_cksum_bad", 0),
        }

    def metrics(self):
        generated_at = int(time.time())
        pools = self.pools()
        vdevs = self.status(pools)
        for pool in pools.values():
            epoch = pool["last_scrub_epoch"]
            if isinstance(epoch, int):
                pool["last_scrub_age"] = max(0, generated_at - epoch)
        result = {
            "generated_at": generated_at,
            "pools": pools,
            "vdevs": vdevs,
            "datasets": self.datasets(),
            "secure": self.secure_dataset(),
            "arc": self.arc(),
        }
        result["error_count"] = len(self.errors)
        result["errors"] = self.errors
        return result

    def snapshots(self):
        generated_at = int(time.time())
        datasets = {}
        for dataset_name in LEAF_DATASETS:
            dataset_output = self.run(
                [
                    ZFS,
                    "list",
                    "-H",
                    "-p",
                    "-o",
                    "name,used,usedbysnapshots",
                    dataset_name,
                ]
            )
            fields = dataset_output.strip().split("\t")
            if len(fields) != 3:
                continue
            used_bytes = self.number(fields[1]) or 0
            retained_bytes = self.number(fields[2]) or 0
            datasets[fields[0]] = {
                "name": fields[0],
                "count": 0,
                "dataset_used_bytes": used_bytes,
                "retained_bytes": retained_bytes,
                "retained_percent": (
                    round(retained_bytes * 100 / used_bytes, 4)
                    if used_bytes
                    else 0
                ),
                "snapshot_unique_bytes_sum": 0,
                "oldest_creation": 0,
                "oldest_age": 0,
                "newest_creation": 0,
                "newest_age": 0,
            }

        for dataset_name in LEAF_DATASETS:
            snapshot_output = self.run(
                [
                    ZFS,
                    "list",
                    "-H",
                    "-p",
                    "-d",
                    "1",
                    "-t",
                    "snapshot",
                    "-o",
                    "name,creation,used",
                    dataset_name,
                ]
            )
            for line in snapshot_output.splitlines():
                fields = line.split("\t")
                if len(fields) != 3 or "@" not in fields[0]:
                    continue
                creation = self.number(fields[1])
                used = self.number(fields[2]) or 0
                summary = datasets.get(dataset_name)
                if summary is None:
                    continue
                summary["count"] += 1
                summary["snapshot_unique_bytes_sum"] += used
                if not isinstance(creation, int):
                    continue
                if summary["oldest_creation"] == 0 or creation < summary["oldest_creation"]:
                    summary["oldest_creation"] = creation
                if summary["newest_creation"] == 0 or creation > summary["newest_creation"]:
                    summary["newest_creation"] = creation

        for summary in datasets.values():
            if summary["oldest_creation"] != 0:
                summary["oldest_age"] = generated_at - summary["oldest_creation"]
                summary["newest_age"] = generated_at - summary["newest_creation"]

        return {
            "generated_at": generated_at,
            "total_count": sum(item["count"] for item in datasets.values()),
            "datasets": datasets,
            "error_count": len(self.errors),
            "errors": self.errors,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("metrics", "snapshots"))
    args = parser.parse_args()

    collector = Collector()
    result = collector.metrics() if args.mode == "metrics" else collector.snapshots()
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
