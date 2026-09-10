#!/usr/bin/env python3
"""Set file logging before qBittorrent starts without replacing other settings."""
import configparser
import io
import json
import os
import stat
from pathlib import Path

from qbittorrent_helpers import password_value


def main():
    path = Path("/config/qBittorrent/qBittorrent.conf")
    configuration = configparser.RawConfigParser(delimiters=("=",), strict=False)
    configuration.optionxform = str
    configuration.read(path)
    if not configuration.has_section("Application"):
        configuration.add_section("Application")
    desired = {"Enabled": "true", "Path": "/config/qBittorrent/logs", "Backup": "true", "DeleteOld": "true", "MaxSizeBytes": "10485760", "Age": "7", "AgeType": "0"}
    changed = any(configuration.get("Application", "FileLogger\\" + key, fallback=None) != value for key, value in desired.items())
    if not configuration.has_section("Preferences"):
        configuration.add_section("Preferences")
    preferences = {
        "WebUI\\Username": "private-cloud",
        "WebUI\\Password_PBKDF2": password_value(
            os.environ["QBITTORRENT_PASSWORD"],
            configuration.get("Preferences", "WebUI\\Password_PBKDF2", fallback=""),
        ),
    }
    changed |= any(configuration.get("Preferences", key, fallback=None) != value for key, value in preferences.items())
    if changed:
        for key, value in preferences.items():
            configuration.set("Preferences", key, value)
        for key, value in desired.items():
            configuration.set("Application", "FileLogger\\" + key, value)
        output = io.StringIO()
        configuration.write(output, space_around_delimiters=False)
        existing = path.stat()
        temporary = path.with_suffix(".logging.tmp")
        temporary.write_text(output.getvalue())
        temporary.chmod(stat.S_IMODE(existing.st_mode))
        if os.geteuid() == 0:
            os.chown(temporary, existing.st_uid, existing.st_gid)
        temporary.replace(path)
    print(json.dumps({"changed": changed}))


if __name__ == "__main__":
    main()
