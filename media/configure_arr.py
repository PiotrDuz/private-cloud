#!/usr/bin/env python3
"""Connect the private ARR services without selecting content providers."""
import json
import sys

from arr_helpers import Arr, configure_download_client, configure_prowlarr, configure_root, read_api_key


def main():
    config = json.load(sys.stdin)
    clients = {}
    for name, port, version in (('sonarr', 8989, 3), ('radarr', 7878, 3), ('prowlarr', 9696, 1)):
        key = read_api_key('/' + config['datasets'][name] + '/config.xml')
        clients[name] = Arr(f"http://{config['addresses'][name]}:{port}/api/v{version}", key)
        clients[name].wait_ready()
    changed = False
    for name, directory in (('sonarr', 'tv'), ('radarr', 'movies')):
        changed |= configure_root(clients[name], '/media/' + directory)
        changed |= configure_download_client(clients[name], name, config['qbittorrent_password'])
        changed |= configure_prowlarr(clients['prowlarr'], name, clients[name].key)
    print(json.dumps({'changed': changed}))


if __name__ == '__main__':
    main()
