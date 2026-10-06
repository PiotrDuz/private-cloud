"""Build qBittorrent's salted WebUI password without changing a valid hash."""
import base64
import hashlib
import hmac
import secrets


def password_value(password, existing):
    value = existing.strip('"')
    if value.startswith('@ByteArray(') and value.endswith(')'):
        value = value[11:-1]
    try:
        salt, expected = (base64.b64decode(part, validate=True) for part in value.split(':'))
        actual = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, 100000)
        if hmac.compare_digest(actual, expected):
            return existing
    except (ValueError, TypeError):
        pass
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha512', password.encode(), salt, 100000)
    return '"@ByteArray(' + base64.b64encode(salt).decode() + ':' + base64.b64encode(digest).decode() + ')"'
