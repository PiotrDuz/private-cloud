#!/usr/bin/env python3
"""Install the pinned Jellyfin OIDC plugin before the server starts."""
import hashlib
import io
import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

PLUGINS_ROOT = Path('/config/plugins')
ASSEMBLY_NAME = 'Jellyfin.Plugin.OIDC.dll'


def main():
    directory = PLUGINS_ROOT / f"{os.environ['JELLYFIN_OIDC_PLUGIN_NAME']}_{os.environ['JELLYFIN_OIDC_PLUGIN_VERSION']}"
    if not (directory / ASSEMBLY_NAME).exists() or not (directory / 'meta.json').exists():
        remove_previous(directory)
        extract_archive(download_archive(), directory)
    enable_plugin(directory)


def download_archive():
    with urllib.request.urlopen(os.environ['JELLYFIN_OIDC_PLUGIN_URL'], timeout=120) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != os.environ['JELLYFIN_OIDC_PLUGIN_SHA256']:
        raise ValueError('OIDC plugin archive checksum mismatch')
    return archive


def extract_archive(archive, directory):
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        if any(Path(member).name != member for member in bundle.namelist()):
            raise ValueError('OIDC plugin archive has an unexpected layout')
        directory.mkdir(parents=True, exist_ok=True)
        bundle.extractall(directory)


def remove_previous(directory):
    for path in PLUGINS_ROOT.glob('*'):
        if path != directory and (path / ASSEMBLY_NAME).exists():
            shutil.rmtree(path)


def enable_plugin(directory):
    path = directory / 'meta.json'
    manifest = json.loads(path.read_text())
    manifest.update(status='Active', autoUpdate=False)
    content = json.dumps(manifest, indent=2) + '\n'
    if path.read_text() != content:
        path.write_text(content)


if __name__ == '__main__':
    main()
