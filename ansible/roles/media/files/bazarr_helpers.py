"""Idempotent Bazarr configuration through its settings API."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

PORTS = {'sonarr': 8989, 'radarr': 7878}


def configure_bazarr(client, keys):
    """Connect Bazarr to Sonarr and Radarr; languages and subtitle providers stay operator choices."""
    desired = bazarr_connections(keys)
    changed = _connection_state(client.request('GET', '/system/settings')) != desired
    if changed:
        form = {}
        for name, settings in desired.items():
            form[f'settings-general-use_{name}'] = 'true'
            form.update({f'settings-{name}-{key}': str(value).lower() if isinstance(value, bool) else str(value) for key, value in settings.items()})
        client.request('POST', '/system/settings', form)
        if _connection_state(client.request('GET', '/system/settings')) != desired:
            raise RuntimeError('Bazarr did not persist its Sonarr and Radarr connections')
    return changed


def bazarr_connections(keys):
    """Bazarr stores an empty base URL for the application root."""
    return {
        name: {'ip': f'{name}.media.svc.cluster.local', 'port': port, 'base_url': '', 'ssl': False, 'apikey': keys[name]}
        for name, port in PORTS.items()
    }


def bazarr_connection_state(client):
    return _connection_state(client.request('GET', '/system/settings'))


def read_bazarr_key(path):
    for attempt in range(30):
        try:
            key = (yaml.safe_load(open(path)) or {}).get('auth', {}).get('apikey')
            if key:
                return key
        except (FileNotFoundError, yaml.YAMLError):
            pass
        time.sleep(2)
    raise RuntimeError('Bazarr did not create its API key')


def _connection_state(settings):
    return {
        name: {key: settings[name].get(key) for key in ('ip', 'port', 'base_url', 'ssl', 'apikey')}
        for name in PORTS
        if settings['general'].get('use_' + name)
    }


class Bazarr:
    def __init__(self, endpoint, key):
        self.endpoint = endpoint
        self.key = key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, form=None):
        payload = urllib.parse.urlencode(form).encode() if form is not None else None
        request = urllib.request.Request(self.endpoint + path, data=payload, method=method, headers={'X-API-KEY': self.key})
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Bazarr API {method} {path} returned HTTP {error.code}') from None

    def wait_ready(self):
        for attempt in range(30):
            try:
                self.request('GET', '/system/status')
                return
            except (RuntimeError, urllib.error.URLError, TimeoutError):
                time.sleep(2)
        raise RuntimeError('Bazarr API did not become ready')
