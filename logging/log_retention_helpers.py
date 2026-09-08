"""Retain active diagnostics while pruning old closed FFmpeg files."""
import os
from pathlib import Path
import time


def prune_diagnostics(directory, max_age, max_bytes):
    if not directory.is_dir() or directory.is_symlink():
        return {"removed": 0, "bytes": 0}
    active = open_inodes()
    candidates = []
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or not path.name.lower().startswith("ffmpeg") or path.suffix.lower() not in {".txt", ".log"}:
            continue
        details = path.stat()
        candidates.append((details.st_mtime, path, details))
    total = sum(details.st_size for _, _, details in candidates)
    removed = 0
    cutoff = time.time() - max_age
    for modified, path, details in sorted(candidates):
        if (details.st_dev, details.st_ino) in active or modified > time.time() - 3600:
            continue
        if modified >= cutoff and total <= max_bytes:
            continue
        current = path.stat(follow_symlinks=False)
        if (current.st_ino, current.st_mtime_ns, current.st_size) != (details.st_ino, details.st_mtime_ns, details.st_size):
            continue
        path.unlink()
        total -= details.st_size
        removed += 1
    return {"removed": removed, "bytes": total}


def open_inodes():
    active = set()
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            for descriptor in (process / "fd").iterdir():
                try:
                    details = descriptor.stat()
                    active.add((details.st_dev, details.st_ino))
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
    return active
