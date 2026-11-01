"""Idempotent configuration through the native ARR APIs."""
import copy
import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

QUALITY_SOURCES = ('HDTV-', 'WEBDL-', 'WEBRip-', 'Bluray-', 'Remux-')
TOP_GROUP_ID = 1000
MINIMUM_SEEDERS = 5


def configure_root(client, path):
    if any(item['path'] == path for item in client.request('GET', '/rootfolder')):
        return False
    client.request('POST', '/rootfolder', {'path': path})
    if not any(item['path'] == path for item in client.request('GET', '/rootfolder')):
        raise RuntimeError('ARR root folder was not persisted')
    return True


def configure_quality_profile(client, preset):
    profiles = client.request('GET', '/qualityprofile')
    existing = next((profile for profile in profiles if profile['name'] == 'private-cloud'), None)
    desired = desired_quality_profile(existing or next((profile for profile in profiles if profile['name'] == 'Any'), profiles[0]), preset)
    changed = existing is None or _quality_profile_state(existing) != _quality_profile_state(desired)
    if changed:
        if existing:
            desired['id'] = existing['id']
            client.request('PUT', '/qualityprofile/' + str(existing['id']), desired)
        else:
            client.request('POST', '/qualityprofile', desired)
    stored = next(profile for profile in client.request('GET', '/qualityprofile') if profile['name'] == 'private-cloud')
    if _quality_profile_state(stored) != _quality_profile_state(desired):
        raise RuntimeError('ARR did not persist the managed quality profile')
    return changed


def desired_quality_profile(profile, preset):
    """Every quality at the selected resolution, Remux included, shares one rank so seeders choose among them."""
    resolution = int(preset[:-1])
    lower, top = [], []
    for quality in _flat_qualities(profile['items']):
        allowed = 720 <= quality.get('resolution', 0) <= resolution and quality['name'].startswith(QUALITY_SOURCES)
        entry = {'quality': quality, 'items': [], 'allowed': allowed}
        (top if allowed and quality['resolution'] == resolution else lower).append(entry)
    if not top:
        raise RuntimeError('ARR exposes no qualities for the selected profile')
    desired = copy.deepcopy(profile)
    desired.pop('id', None)
    desired.update(name='private-cloud', upgradeAllowed=True, cutoff=TOP_GROUP_ID,
                   items=lower + [{'name': preset, 'id': TOP_GROUP_ID, 'items': top, 'allowed': True}])
    return desired


def configure_minimum_seeders(prowlarr, applications):
    """Prowlarr syncs its app profile minimum, but skips failing indexers, so the ARR indexers are set directly too."""
    changed = False
    for profile in prowlarr.request('GET', '/appprofile'):
        if profile.get('minimumSeeders') != MINIMUM_SEEDERS:
            prowlarr.request('PUT', '/appprofile/' + str(profile['id']), {**profile, 'minimumSeeders': MINIMUM_SEEDERS})
            changed = True
    if any(profile.get('minimumSeeders') != MINIMUM_SEEDERS for profile in prowlarr.request('GET', '/appprofile')):
        raise RuntimeError('Prowlarr did not persist the minimum seeders')
    for client in applications:
        for indexer in lagging_seeder_indexers(client):
            for field in indexer['fields']:
                if field['name'] == 'minimumSeeders':
                    field['value'] = MINIMUM_SEEDERS
            # forceSave skips the connection test that a temporarily failing indexer would fail.
            client.request('PUT', f"/indexer/{indexer['id']}?forceSave=true", indexer)
            changed = True
        if lagging_seeder_indexers(client):
            raise RuntimeError('ARR did not persist the minimum seeders')
    return changed


def lagging_seeder_indexers(client):
    return [
        indexer for indexer in client.request('GET', '/indexer')
        if indexer.get('protocol') == 'torrent'
        and any(field['name'] == 'minimumSeeders' and field.get('value') != MINIMUM_SEEDERS for field in indexer['fields'])
    ]


def configure_download_client(client, name, password):
    fields = {
        'host': 'qbittorrent.media.svc.cluster.local', 'port': 8080,
        'useSsl': False, 'username': 'private-cloud', 'password': password,
        'tvCategory' if name == 'sonarr' else 'movieCategory': name,
    }
    return client.upsert('/downloadclient', 'QBittorrent', 'private-cloud-qbittorrent', fields, {'enable': True, 'removeCompletedDownloads': True})


def configure_prowlarr(client, name, key):
    port = 8989 if name == 'sonarr' else 7878
    fields = {
        'prowlarrUrl': 'http://prowlarr.media.svc.cluster.local:9696',
        'baseUrl': f'http://{name}.media.svc.cluster.local:{port}',
        'apiKey': key,
    }
    return client.upsert('/applications', name.title(), 'private-cloud-' + name, fields, {'syncLevel': 'fullSync'})


def configure_flaresolverr(client):
    """Indexers tagged flaresolverr solve Cloudflare challenges through the FlareSolverr proxy."""
    tag = next((item for item in client.request('GET', '/tag') if item['label'] == 'flaresolverr'), None)
    created = tag is None
    if created:
        tag = client.request('POST', '/tag', {'label': 'flaresolverr'})
    fields = {'host': 'http://flaresolverr.media.svc.cluster.local:8191/', 'requestTimeout': 60}
    return client.upsert('/indexerProxy', 'FlareSolverr', 'private-cloud-flaresolverr', fields, {'tags': [tag['id']]}) or created


def _connection_state_without_write_only_values(connection):
    state = copy.deepcopy(connection)
    for field in state.get('fields', []):
        if field.get('name') in {'password', 'apiKey'}:
            field.pop('value', None)
    return state


def read_api_key(path):
    for attempt in range(30):
        try:
            key = ET.parse(path).getroot().findtext('ApiKey')
            if key:
                return key
        except (FileNotFoundError, ET.ParseError):
            pass
        time.sleep(2)
    raise RuntimeError('ARR did not create its API key')


def _flat_qualities(items):
    for item in items:
        if item.get('items'):
            yield from _flat_qualities(item['items'])
        else:
            yield item['quality']


def _quality_profile_state(profile):
    return {
        'name': profile['name'],
        'upgradeAllowed': profile['upgradeAllowed'],
        'cutoff': profile['cutoff'],
        'items': _quality_item_state(profile['items']),
    }


def _quality_item_state(items):
    return [
        {
            'id': (item.get('quality') or {}).get('id', item.get('id')),
            'allowed': item.get('allowed', False),
            'items': _quality_item_state(item.get('items') or []),
        }
        for item in items
    ]


class Arr:
    def __init__(self, endpoint, key):
        self.endpoint = endpoint
        self.key = key
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None):
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.endpoint + path, data=payload, method=method,
                                         headers={'X-Api-Key': self.key, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'ARR API {method} {path} returned HTTP {error.code}') from None

    def wait_ready(self):
        for attempt in range(30):
            try:
                self.request('GET', '/system/status')
                return
            except (RuntimeError, urllib.error.URLError, TimeoutError):
                time.sleep(2)
        raise RuntimeError('ARR API did not become ready')

    def upsert(self, route, implementation, name, fields, settings):
        existing = next((item for item in self.request('GET', route) if item['name'] == name), None)
        schema = next(item for item in self.request('GET', route + '/schema') if item['implementation'] == implementation)
        desired = copy.deepcopy(existing or schema)
        desired.update(name=name, **settings)
        available = {field['name']: field for field in desired['fields']}
        if not fields.keys() <= available.keys():
            raise RuntimeError('ARR schema is missing a managed field')
        for field, value in fields.items():
            available[field]['value'] = value
        changed = (
            existing is None
            or _connection_state_without_write_only_values(existing)
            != _connection_state_without_write_only_values(desired)
        )
        has_write_only_fields = any(field in {'password', 'apiKey'} for field in fields)
        if changed or has_write_only_fields:
            route_id = route + '/' + str(existing['id']) if existing else route
            self.request('PUT' if existing else 'POST', route_id, desired)
        stored = next(item for item in self.request('GET', route) if item['name'] == name)
        actual = {field['name']: field.get('value') for field in stored['fields']}
        for field, value in fields.items():
            if field not in ('password', 'apiKey') and actual.get(field) != value:
                raise RuntimeError('ARR did not persist a managed connection field')
        return changed
