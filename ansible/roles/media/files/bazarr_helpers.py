"""Idempotent Bazarr configuration through its settings API."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

PORTS = {'sonarr': 8989, 'radarr': 7878}
LANGUAGE_PROFILE = 'private-cloud'


def configure_bazarr(client, keys):
    """Connect Bazarr to Sonarr and Radarr; subtitle providers stay operator choices."""
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


def configure_bazarr_languages(client, languages):
    """Maintain the managed language profile as the default and give it to series and movies that have none."""
    enabled = {language['code2'] for language in client.request('GET', '/system/languages') if language['enabled']}
    profiles = client.request('GET', '/system/languages/profiles')
    managed = next((profile for profile in profiles if profile['name'] == LANGUAGE_PROFILE), None)
    desired = desired_language_profile(managed, profiles, languages)
    changed = False
    if not set(languages) <= enabled or managed != desired:
        # Bazarr deletes every profile missing from the posted list, so the operator's other profiles are posted back unchanged.
        others = [profile for profile in profiles if profile['name'] != LANGUAGE_PROFILE]
        form = [('languages-enabled', code) for code in sorted(enabled | set(languages))]
        client.request('POST', '/system/settings', form + [('languages-profiles', json.dumps(others + [desired]))])
        changed = True
    if bazarr_language_defaults(client) != desired['profileId']:
        client.request('POST', '/system/settings', {
            **{f'settings-general-{kind}_default_enabled': 'true' for kind in ('serie', 'movie')},
            **{f'settings-general-{kind}_default_profile': str(desired['profileId']) for kind in ('serie', 'movie')},
        })
        changed = True
    for route, key in (('/series', 'sonarrSeriesId'), ('/movies', 'radarrId')):
        missing = [item[key] for item in client.request('GET', route + '?start=0&length=-1')['data'] if item['profileId'] is None]
        if missing:
            field = 'seriesid' if route == '/series' else 'radarrid'
            client.request('POST', route, [(field, str(item)) for item in missing] + [('profileid', str(desired['profileId'])) for _ in missing])
            changed = True
    if bazarr_language_state(client) != bazarr_language_target(languages):
        raise RuntimeError('Bazarr did not persist its managed language profile and defaults')
    return changed


def desired_language_profile(managed, profiles, languages):
    profile_id = managed['profileId'] if managed else max((profile['profileId'] for profile in profiles), default=0) + 1
    return {
        'profileId': profile_id,
        'name': LANGUAGE_PROFILE,
        'cutoff': None,
        'items': [
            {'id': index, 'language': code, 'audio_exclude': 'False', 'audio_only_include': 'False', 'hi': 'False', 'forced': 'False'}
            for index, code in enumerate(languages, 1)
        ],
        'mustContain': [],
        'mustNotContain': [],
        'originalFormat': 0,
        'tag': None,
    }


def bazarr_language_target(languages):
    return {'default': True, 'languages': list(languages)}


def bazarr_language_state(client):
    """Report the managed profile's languages and whether series and movies default to it."""
    profile = next((profile for profile in client.request('GET', '/system/languages/profiles') if profile['name'] == LANGUAGE_PROFILE), None)
    if profile is None:
        return None
    return {'default': bazarr_language_defaults(client) == profile['profileId'], 'languages': [item['language'] for item in profile['items']]}


def bazarr_language_defaults(client):
    """Return the profile ID that both series and movies default to, or None when they differ or are disabled."""
    general = client.request('GET', '/system/settings')['general']
    if not general.get('serie_default_enabled') or not general.get('movie_default_enabled'):
        return None
    return general.get('serie_default_profile') if general.get('serie_default_profile') == general.get('movie_default_profile') else None


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
