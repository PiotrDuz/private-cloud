"""Edit Jellyfin's persisted configuration while its server is stopped."""
import xml.etree.ElementTree as ET


def configure_server(path):
    root = read_xml(path, 'ServerConfiguration')
    set_value(root, 'EnableExternalContentInSuggestions', 'false')
    set_value(root, 'QuickConnectAvailable', 'true')
    return write_xml(path, root)


def configure_library(path, location=None):
    root = read_xml(path, 'LibraryOptions')
    if location and root.find('PathInfos') is None:
        info = ET.SubElement(ET.SubElement(root, 'PathInfos'), 'MediaPathInfo')
        set_value(info, 'Path', location)
    for key in ('SaveLocalMetadata', 'SaveSubtitlesWithMedia', 'SaveLyricsWithMedia', 'SaveTrickplayWithMedia', 'AutomaticallyAddToCollection'):
        set_value(root, key, 'false')
    set_value(root, 'AutomaticRefreshIntervalDays', '0')
    for key in ('SubtitleDownloadLanguages', 'SubtitleFetcherOrder', 'LyricFetcherOrder', 'MetadataSavers'):
        clear_element(root, key)
    return write_xml(path, root)


def configure_branding(path, hostname):
    root = read_xml(path, 'BrandingOptions')
    set_value(root, 'LoginDisclaimer', login_disclaimer(hostname))
    return write_xml(path, root)


def configure_oidc(path, issuer, client_id, client_secret):
    root = ET.Element('PluginConfiguration')
    provider = ET.SubElement(ET.SubElement(root, 'Providers'), 'OidcProviderConfig')
    set_values(provider, {
        'ProviderId': 'keycloak',
        'DisplayName': 'Keycloak',
        'Authority': issuer,
        'ClientId': client_id,
        'ClientSecret': client_secret,
        'Scopes': 'openid profile email',
        'RoleClaim': 'realm_access.roles',
        'UsernameClaim': 'preferred_username',
        'DisplayNameClaim': 'name',
        'PictureClaim': 'picture',
        'SyncProfileImage': 'false',
        'Enabled': 'true',
        'ButtonColor': '#4285F4',
        'StrictAccessTokenValidation': 'true',
        'AllowLoopbackAuthority': 'false',
        'AllowLinkLocalAuthority': 'false',
    })
    retain_pins(path, provider)
    mappings = ET.SubElement(root, 'RoleMappings')
    add_role_mapping(mappings, 'jellyfin-admins', administrator=True, all_libraries=True)
    add_role_mapping(mappings, 'jellyfin-users', administrator=False, all_libraries=False, libraries=['Movies', 'TV'])
    set_values(root, {'AutoCreateUsers': 'true', 'MigrateLocalUsers': 'false', 'SyncDisplayName': 'false', 'BlockPrivateNetworkAuthorities': 'false'})
    return write_xml(path, root)


def read_xml(path, name):
    root = ET.parse(path).getroot() if path.exists() else ET.Element(name)
    if root.tag != name:
        raise ValueError(f'Unexpected Jellyfin configuration root in {path.name}')
    return root


def set_value(root, name, value):
    element = root.find(name)
    if element is None:
        element = ET.SubElement(root, name)
    element.text = value


def set_values(root, values):
    for name, value in values.items():
        set_value(root, name, value)


def clear_element(root, name):
    element = root.find(name)
    if element is None:
        element = ET.SubElement(root, name)
    element.clear()
    return element


def add_role_mapping(parent, role, administrator, all_libraries, libraries=()):
    mapping = ET.SubElement(parent, 'RoleMapping')
    set_values(mapping, {
        'RoleName': role,
        'ProviderFilter': 'keycloak',
        'IsAdmin': bool_value(administrator),
        'EnableAllLibraries': bool_value(all_libraries),
        'EnableMediaPlayback': 'true',
        'EnableRemoteAccess': 'true',
        'EnableTranscoding': 'true',
    })
    if libraries:
        names = ET.SubElement(mapping, 'LibraryNames')
        for library in libraries:
            ET.SubElement(names, 'string').text = library


def retain_pins(path, provider):
    if not path.exists():
        return
    previous = ET.parse(path).getroot()
    for name in ('PinnedAuthority', 'PinnedIssuer', 'PinnedTokenEndpoint', 'PinnedJwksUri'):
        element = previous.find(f'Providers/OidcProviderConfig/{name}')
        if element is not None and element.text:
            set_value(provider, name, element.text)


def login_disclaimer(hostname):
    link = f'https://{hostname}/sso/OIDC/Start/keycloak'
    return (
        '<div style="margin:1em 0;text-align:center;">'
        f'<a href="{link}" style="display:block;margin:0.5em auto;padding:0.7em 1.5em;background:#4285F4;color:#fff;text-decoration:none;border-radius:4px;font-size:1em;max-width:300px;">Sign in with Keycloak</a>'
        '<div style="margin:1em 0;color:#888;">— or sign in with password —</div>'
        '</div>'
    )


def bool_value(value):
    return 'true' if value else 'false'


def write_xml(path, root):
    ET.indent(root)
    return write_file(path, ET.tostring(root, encoding='unicode', xml_declaration=True) + '\n')


def write_file(path, content):
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content)
    temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temporary.replace(path)
    return True
