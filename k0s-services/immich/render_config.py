#!/usr/bin/env python3
"""Render the Immich configuration file with OAuth settings from the environment."""
import json
import os
from pathlib import Path

OUTPUT_PATH = Path('/config/immich-config.json')


def main():
    configuration = {'oauth': oauth_configuration()}
    OUTPUT_PATH.write_text(json.dumps(configuration, indent=2, sort_keys=True) + '\n')


def oauth_configuration():
    return {
        'enabled': boolean('IMMICH_OAUTH_ENABLED'),
        'issuerUrl': os.environ['IMMICH_OAUTH_ISSUER_URL'],
        'clientId': os.environ['IMMICH_OAUTH_CLIENT_ID'],
        'clientSecret': os.environ['IMMICH_OAUTH_CLIENT_SECRET'],
        'scope': os.environ.get('IMMICH_OAUTH_SCOPE', 'openid email profile'),
        'autoRegister': boolean('IMMICH_OAUTH_AUTO_REGISTER'),
        'autoLaunch': boolean('IMMICH_OAUTH_AUTO_LAUNCH'),
        'mobileOverrideEnabled': boolean('IMMICH_OAUTH_MOBILE_OVERRIDE_ENABLED'),
        'mobileRedirectUri': os.environ.get('IMMICH_OAUTH_MOBILE_REDIRECT_URI', ''),
        'roleClaim': os.environ.get('IMMICH_OAUTH_ROLE_CLAIM', 'immich_role'),
        'storageLabelClaim': os.environ.get('IMMICH_OAUTH_STORAGE_LABEL_CLAIM', 'preferred_username'),
        'tokenEndpointAuthMethod': os.environ.get('IMMICH_OAUTH_TOKEN_ENDPOINT_AUTH_METHOD', 'client_secret_post'),
    }


def boolean(name):
    return os.environ.get(name, 'false').strip().lower() in {'1', 'true', 'yes'}


if __name__ == '__main__':
    main()
