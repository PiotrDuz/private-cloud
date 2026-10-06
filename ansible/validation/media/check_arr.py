#!/usr/bin/env python3
"""Verify configured Sonarr, Radarr, and Prowlarr APIs."""

import json
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "roles" / "media" / "files"))

from arr_helpers import Arr, _configure_quality_items, _quality_profile_state, read_api_key


def main():
    config = json.load(sys.stdin)
    clients = {}
    for name, port, version in (("sonarr", 8989, 3), ("radarr", 7878, 3), ("prowlarr", 9696, 1)):
        api_key = read_api_key("/" + config["datasets"][name] + "/config.xml")
        clients[name] = Arr(f"http://{config['addresses'][name]}:{port}/api/v{version}", api_key)
        clients[name].wait_ready()

    for name, directory in (("sonarr", "tv"), ("radarr", "movies")):
        validate_quality_profile(clients[name], config["quality_profiles"][name])
        validate_root_folder(clients[name], "/media/" + directory)
        validate_download_client(clients[name], name)
        validate_prowlarr_application(clients["prowlarr"], name)

    print(json.dumps({"services": ["sonarr", "radarr", "prowlarr"], "result": "passed"}, separators=(",", ":")))


def validate_quality_profile(client, preset):
    profiles = client.request("GET", "/qualityprofile")
    profile = next((item for item in profiles if item["name"] == "private-cloud"), None)
    if profile is None:
        raise RuntimeError("ARR is missing its managed quality profile")

    desired = copy.deepcopy(profile)
    qualities = _configure_quality_items(desired["items"], int(preset[:-1]))
    cutoff_name = "Bluray-" + preset
    cutoff = next((quality_id for name, quality_id in qualities if name == cutoff_name), None)
    if cutoff is None:
        raise RuntimeError("ARR is missing the requested quality cutoff")
    desired["upgradeAllowed"] = True
    desired["cutoff"] = cutoff
    if _quality_profile_state(profile) != _quality_profile_state(desired):
        raise RuntimeError("ARR quality profile differs from global configuration")


def validate_root_folder(client, path):
    folders = client.request("GET", "/rootfolder")
    if not any(folder.get("path") == path for folder in folders):
        raise RuntimeError("ARR is missing a managed library folder")


def validate_download_client(client, application):
    clients = client.request("GET", "/downloadclient")
    download_client = next((item for item in clients if item.get("name") == "private-cloud-qbittorrent"), None)
    if download_client is None or download_client.get("implementation") != "QBittorrent":
        raise RuntimeError("ARR is missing its qBittorrent download client")
    fields = {field["name"]: field.get("value") for field in download_client.get("fields", [])}
    category_field = "tvCategory" if application == "sonarr" else "movieCategory"
    expected = {
        "host": "qbittorrent.media.svc.cluster.local",
        "port": 8080,
        "useSsl": False,
        "username": "private-cloud",
        category_field: application,
    }
    if any(fields.get(name) != value for name, value in expected.items()):
        raise RuntimeError("ARR qBittorrent connection differs from the managed settings")


def validate_prowlarr_application(client, application):
    applications = client.request("GET", "/applications")
    configured = next((item for item in applications if item.get("name") == "private-cloud-" + application), None)
    if configured is None or configured.get("implementation") != application.title():
        raise RuntimeError("Prowlarr is missing a managed ARR application")
    fields = {field["name"]: field.get("value") for field in configured.get("fields", [])}
    port = 8989 if application == "sonarr" else 7878
    expected = {
        "prowlarrUrl": "http://prowlarr.media.svc.cluster.local:9696",
        "baseUrl": f"http://{application}.media.svc.cluster.local:{port}",
    }
    if configured.get("syncLevel") != "fullSync" or any(fields.get(name) != value for name, value in expected.items()):
        raise RuntimeError("Prowlarr's managed ARR application differs from service configuration")


if __name__ == "__main__":
    main()
