"""Remote agent settings and read-only polling. No remote commands are executed."""
import ipaddress
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit
import httpx


def validate_server(server):
    allowed = {'id', 'name', 'kind', 'os', 'agentUrl', 'token', 'enabled'}
    if not isinstance(server, dict) or set(server) - allowed:
        raise ValueError('Unsupported server fields')
    for key in ['id', 'name']:
        if not isinstance(server.get(key), str) or not server[key].strip() or len(server[key]) > 100:
            raise ValueError('Each server needs an id and name (up to 100 characters)')
    if server['id'] == '__watcher__' or server.get('kind') != 'remote' or server.get('os') != 'ubuntu' or type(server.get('enabled')) is not bool:
        raise ValueError('Remote servers must use Ubuntu and a valid enable switch')
    url = server.get('agentUrl', '')
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Enter a valid agent URL')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ['http', 'https'] or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError()
        if parsed.path != '/v1/metrics' or (parsed.port is not None and not 1 <= parsed.port <= 65535):
            raise ValueError()
        if parsed.scheme == 'http':
            if parsed.hostname != 'localhost':
                address = ipaddress.ip_address(parsed.hostname)
                networks = ['127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '::1/128', 'fc00::/7']
                if not any(address in ipaddress.ip_network(network) for network in networks):
                    raise ValueError()
    except ValueError:
        raise ValueError('Agent URL must end with /v1/metrics. Use HTTPS, or HTTP on a private/VPN or loopback IP address')
    token = server.get('token', '')
    if not isinstance(token, str) or (token and (not 32 <= len(token) <= 512 or not token.isascii() or any(c.isspace() for c in token))):
        raise ValueError('Agent token must contain 32–512 non-whitespace ASCII characters')
    if server['enabled'] and not token:
        raise ValueError('An enabled server requires an agent token')
    return server


def clean_servers(servers):
    return [{**{key: value for key, value in server.items() if key != 'token'}, 'hasToken': bool(server.get('token'))} for server in servers]


def validate_metrics(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported response')
    for key in ['cpu_percent', 'ram_percent', 'disk_percent', 'disk_free_bytes', 'disk_total_bytes', 'uptime_seconds']:
        value = data.get(key)
        if type(value) not in [int, float] or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid metric')
        if key.endswith('_percent') and value > 100:
            raise ValueError('Invalid percentage')
    if data['disk_total_bytes'] <= 0 or data['disk_free_bytes'] > data['disk_total_bytes']:
        raise ValueError('Invalid disk capacity')
    measured = datetime.fromisoformat(data['collected_at'])
    if measured.tzinfo is None or abs((datetime.now(timezone.utc) - measured).total_seconds()) > 300:
        raise ValueError('Stale agent response or clock mismatch')
    return data


def metric_checks(data):
    checks = {}
    for label, key, warning, critical in [('CPU', 'cpu_percent', 75, 90), ('RAM', 'ram_percent', 80, 92), ('Disk', 'disk_percent', 80, 90)]:
        value = data[key]
        checks[label] = {'status': 'critical' if value >= critical else 'warning' if value >= warning else 'ok', 'summary': f'{value:.1f}% used', 'checked_at': data['collected_at']}
    checks['Free disk'] = {'status': checks['Disk']['status'], 'summary': f"{data['disk_free_bytes']/1024**3:.1f} GiB free of {data['disk_total_bytes']/1024**3:.1f} GiB", 'checked_at': data['collected_at']}
    seconds = int(data['uptime_seconds'])
    checks['Uptime'] = {'status': 'ok', 'summary': f'{seconds//86400} days · {seconds%86400//3600} hours', 'checked_at': data['collected_at']}
    return checks


async def poll_server(server, client=None):
    base = {key: server[key] for key in ['id', 'name', 'os', 'enabled']}
    if not server['enabled']:
        return {**base, 'status': 'disabled', 'summary': 'Monitoring disabled', 'checks': {}}
    if client is None:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as connection:
            return await poll_server(server, connection)
    try:
        async with client.stream('GET', server['agentUrl'], headers={'Authorization': 'Bearer ' + server['token']}) as response:
            if response.status_code in [401, 403]:
                return {**base, 'status': 'unknown', 'summary': 'Agent authentication failed · check token', 'checks': {}}
            if response.status_code != 200:
                raise ValueError('Agent unavailable')
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError('Response too large')
        import json
        data = validate_metrics(json.loads(raw))
        checks = metric_checks(data)
        status = next((s for s in ['critical', 'warning'] if any(c['status'] == s for c in checks.values())), 'ok')
        return {**base, 'status': status, 'summary': 'Agent connected', 'checked_at': data['collected_at'], 'checks': checks}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError):
        return {**base, 'status': 'unknown', 'summary': 'Agent unreachable, certificate invalid, or response invalid/stale', 'checks': {}}
