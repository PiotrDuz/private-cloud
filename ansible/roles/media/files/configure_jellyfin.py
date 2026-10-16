#!/usr/bin/env python3
"""Apply local-only Jellyfin settings before the server starts."""
import json
import os
from pathlib import Path

from jellyfin_helpers import configure_library, configure_network, configure_server


def main():
    root = Path('/config')
    changed = configure_server(root / 'config' / 'system.xml')
    changed |= configure_network(root / 'config' / 'network.xml', os.environ['KNOWN_PROXIES'].split(','))
    for name, kind, location in (('Movies', 'movies', '/media/movies'), ('TV', 'tvshows', '/media/tv')):
        directory = root / 'root' / 'default' / name
        if not directory.exists():
            directory.mkdir(parents=True)
            (directory / f'{kind}.collection').touch()
            (directory / 'media.mblink').write_text(location)
            changed = True
        changed |= configure_library(directory / 'options.xml', location)
    for options in (root / 'root' / 'default').glob('*/options.xml'):
        changed |= configure_library(options)
    print(json.dumps({'changed': changed}))


if __name__ == '__main__':
    main()
