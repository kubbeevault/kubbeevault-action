"""Dependency-free loader for the KubbeeVault composite action."""

import json
import os
import re
import sys
import uuid
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward credentials to a redirect destination.
        return None


def mask(value):
    escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::add-mask::' + escaped, flush=True)


def parse_mappings(raw):
    mappings = []
    names = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        key, separator, name = line.rpartition(':')
        key, name = key.strip(), name.strip()
        if not separator or not key or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Invalid mapping; use one secret-key: ENV_NAME per line.')
        upper = name.upper()
        if upper.startswith(('GITHUB_', 'RUNNER_', 'ACTIONS_', 'KV_')) or upper in {
            'PATH', 'HOME', 'SHELL', 'BASH_ENV', 'ENV', 'NODE_OPTIONS',
            'LD_PRELOAD', 'LD_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME',
            'GIT_CONFIG', 'GIT_CONFIG_COUNT', 'GIT_SSH_COMMAND',
        }:
            raise ValueError('Reserved environment variable name.')
        if upper in names:
            raise ValueError('Duplicate environment variable name.')
        names.add(upper)
        mappings.append((key, name))
    if not mappings:
        raise ValueError('At least one secret mapping is required.')
    return mappings


def select_values(vault, mappings):
    if not isinstance(vault, dict) or not isinstance(vault.get('secrets'), list):
        raise ValueError('Invalid vault response.')
    selected = []
    for key, name in mappings:
        matches = [item.get('value') for item in vault['secrets']
                   if isinstance(item, dict) and item.get('key') == key]
        if len(matches) != 1 or not isinstance(matches[0], str):
            raise ValueError('A requested key is missing, duplicated, or has a non-string value.')
        if '\0' in matches[0]:
            raise ValueError('Secret values containing NUL cannot be environment variables.')
        selected.append((name, matches[0]))
    return selected


def serialize(values):
    blocks = []
    for name, value in values:
        delimiter = 'kv_' + uuid.uuid4().hex
        while delimiter in value:
            delimiter = 'kv_' + uuid.uuid4().hex
        blocks.append(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')
    return ''.join(blocks)


def main():
    token = os.environ['KV_TOKEN'].strip()
    if not token:
        raise ValueError('The integration token is empty.')
    mask(token)
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    if not token or any(c.isspace() for c in token):
        raise ValueError('Invalid integration token.')
    mask(token)
    mappings = parse_mappings(os.environ['KV_SECRETS'])
    base = os.environ['KV_URL'].strip().rstrip('/')
    url = urlsplit(base)
    if not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('Invalid server URL.')
    if url.scheme != 'https' and not (
        url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}
    ):
        raise ValueError('HTTPS is required except for loopback development URLs.')
    krn = os.environ['KV_KRN'].strip()
    if not krn or '\r' in krn or '\n' in krn:
        raise ValueError('Invalid vault KRN.')
    request = Request(base + '/vault-app/vaults/integration/GITHUB_ACTIONS', headers={
        'KubbeeAccessToken': 'Bearer ' + token,
        'KubbeeVaultKRN': krn,
        'Accept': 'application/json',
    })
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            vault = json.load(response)
    except Exception:
        # Response bodies and exception details can contain credentials.
        raise ValueError('KubbeeVault request failed; check connectivity, token, KRN, and server status.') from None
    if not isinstance(vault, dict) or vault.get('krn') != krn:
        raise ValueError('The returned vault does not match the requested KRN.')
    values = select_values(vault, mappings)
    for _, value in values:
        mask(value)
    content = serialize(values)
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8', newline='') as env_file:
        env_file.write(content)
    print(f'Loaded {len(values)} secret mapping(s).')


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(f'::error::{error}', file=sys.stderr)
        sys.exit(1)
    except Exception:
        print('::error::Unable to load KubbeeVault secrets.', file=sys.stderr)
        sys.exit(1)
