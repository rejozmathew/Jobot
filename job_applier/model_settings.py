"""Public executor catalog and per-dispatch model selection; no credential storage."""
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit


def executor_kind(config):
    if isinstance(config.get('hermes_desktop'), dict):return 'hermes_desktop'
    command = config.get('hermes_command')
    if not command or Path(command[0]).stem.lower() == 'hermes':return 'hermes_cli'
    return 'external'


def application_selection(config, settings):
    """Read fresh settings once at dispatch, leaving the original runtime/profile intact."""
    result = dict(config)
    if settings.get('application_model_override') and settings.get('reasoning_model'):
        result.update(application_provider=settings['reasoning_provider'],
                      application_model=settings['reasoning_model'],
                      application_effort=settings['reasoning_effort'])
    return result


def _local_provider(row):
    if row.get('slug') in ('llamacpp', 'ollama', 'lmstudio'):return True
    host = urlsplit(row.get('api_url') or row.get('base_url') or '').hostname or ''
    if host == 'localhost' or host.endswith('.local'):return True
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback
    except ValueError:
        return False


def public_catalog(payload):
    """Explicit projection: never forward endpoint URLs, keys or arbitrary RPC metadata."""
    providers = []
    for row in payload.get('providers', []):
        slug = row.get('slug')
        if not isinstance(slug, str) or not slug:continue
        local = _local_provider(row)
        name = 'ChatGPT' if slug == 'openai-codex' else 'Local' if local else row.get('name') or slug
        models = list(dict.fromkeys(m for m in row.get('models', []) if isinstance(m, str) and m))
        capabilities = {m: {'reasoning': c['reasoning']} for m in models
                        if isinstance(c := (row.get('capabilities') or {}).get(m), dict)
                        and type(c.get('reasoning')) is bool}
        providers.append({'id': slug, 'name': name, 'local': local, 'models': models,
                          'capabilities': capabilities})
    return {'provider': payload.get('provider'), 'model': payload.get('model'), 'providers': providers}


def model_catalog(config, *, refresh=False):
    kind = executor_kind(config) if config is not None else 'external'
    result = {'executor': kind, 'status': 'manual', 'providers': [], 'provider': None, 'model': None}
    if kind != 'hermes_desktop':return result
    from .hermes_desktop import connection
    import httpx
    from websockets.exceptions import ConnectionClosed
    options = config['hermes_desktop']
    params = {'explicit_only': True, 'refresh': bool(refresh)}
    if options.get('profile'):params['profile'] = options['profile']
    try:
        with connection(options) as (rpc, _):
            result.update(public_catalog(rpc.call('model.options', params)), status='available')
    except (OSError, ValueError, TypeError, KeyError, TimeoutError, ConnectionClosed, httpx.HTTPError):
        result['status'] = 'unavailable'
    return result
