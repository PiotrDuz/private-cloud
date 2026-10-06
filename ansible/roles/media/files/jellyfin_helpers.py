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


def clear_element(root, name):
    element = root.find(name)
    if element is None:
        element = ET.SubElement(root, name)
    element.clear()
    return element


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
