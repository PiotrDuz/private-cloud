"""Idempotent configuration through the native ARR APIs."""
import copy
import json
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


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
    desired = copy.deepcopy(existing or next((profile for profile in profiles if profile['name'] == 'Any'), profiles[0]))
    desired.pop('id', None)
    desired['name'] = 'private-cloud'
    desired['upgradeAllowed'] = True
    qualities = _configure_quality_items(desired['items'], int(preset[:-1]))
    if not qualities:
        raise RuntimeError('ARR exposes no qualities for the selected profile')
    cutoff_name = 'Bluray-' + preset
    cutoff = next((quality_id for name, quality_id in qualities if name == cutoff_name), None)
    if cutoff is None:
        raise RuntimeError('ARR exposes no Blu-ray quality for the selected profile cutoff')
    desired['cutoff'] = cutoff
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


def configure_download_client(client, name, password):
    fields = {
        'host': 'qbittorrent.media.svc.cluster.local', 'port': 8080,
        'useSsl': False, 'username': 'private-cloud', 'password': password,
        'tvCategory' if name == 'sonarr' else 'movieCategory': name,
    }
    return client.upsert('/downloadclient', 'QBittorrent', 'private-cloud-qbittorrent', fields, {'enable': True})


def configure_prowlarr(client, name, key):
    port = 8989 if name == 'sonarr' else 7878
    fields = {
        'prowlarrUrl': 'http://prowlarr.media.svc.cluster.local:9696',
        'baseUrl': f'http://{name}.media.svc.cluster.local:{port}',
        'apiKey': key,
    }
    return client.upsert('/applications', name.title(), 'private-cloud-' + name, fields, {'syncLevel': 'fullSync'})


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


def _configure_quality_items(items, maximum_resolution):
    qualities = []
    for item in items:
        children = item.get('items') or []
        if children:
            child_qualities = _configure_quality_items(children, maximum_resolution)
            item['allowed'] = bool(child_qualities)
            if child_qualities and 'id' not in item:
                raise RuntimeError('ARR quality group has no cutoff identifier')
            qualities.extend((name, item['id']) for name, _ in child_qualities)
            continue
        quality = item.get('quality') or {}
        name = quality.get('name', '')
        resolution = quality.get('resolution', 0)
        item['allowed'] = (
            720 <= resolution <= maximum_resolution
            and name.startswith(('HDTV-', 'WEBDL-', 'WEBRip-', 'Bluray-'))
            and 'Remux' not in name
        )
        if item['allowed']:
            qualities.append((name, quality['id']))
    return qualities


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
        changed = existing != desired
        if changed:
            route_id = route + '/' + str(existing['id']) if existing else route
            self.request('PUT' if existing else 'POST', route_id, desired)
        stored = next(item for item in self.request('GET', route) if item['name'] == name)
        actual = {field['name']: field.get('value') for field in stored['fields']}
        for field, value in fields.items():
            if field not in ('password', 'apiKey') and actual.get(field) != value:
                raise RuntimeError('ARR did not persist a managed connection field')
        return changed
