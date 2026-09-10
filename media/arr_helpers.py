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
