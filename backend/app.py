from backend.direct_ssh import ALIAS, DIRECT_LABELS, direct_request
from backend.servers import validate_server, clean_servers, poll_server
import copy
import json
import os
import io
import tempfile
from xml.etree.ElementTree import Comment, Element, SubElement, indent, tostring
import asyncio
import math
import socket
import ssl
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from defusedxml import ElementTree
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response


def load_config(path, *, allow_empty=False):
    root = ElementTree.parse(path).getroot()
    if root.tag != 'monitor' or not {'version', 'intervalSeconds'} <= set(root.attrib) or set(root.attrib) - {'version', 'intervalSeconds', 'localMetrics', 'diskPath', 'internetProbes'} or root.get('version') != '1':
        raise ValueError('config.xml: expected <monitor version="1" intervalSeconds="30">')
    interval = int(root.get('intervalSeconds'))
    if not 10 <= interval <= 3600:
        raise ValueError('config.xml: intervalSeconds must be between 10 and 3600')
    if root.get('localMetrics', 'false') not in ['true', 'false']:
        raise ValueError('config.xml: localMetrics must be true or false')
    for target in root.get('internetProbes', '1.1.1.1:443,8.8.8.8:53').split(','):
        try:
            host, port = target.strip().rsplit(':', 1)
            if not host or not 1 <= int(port) <= 65535:
                raise ValueError()
        except ValueError:
            raise ValueError('config.xml: internetProbes must contain comma-separated host:port values')
    apps = []
    ids = set()
    for node in root:
        allowed = {'id', 'name', 'backend', 'siteUrl', 'healthUrl', 'mailHealthUrl', 'diagnosticsUrl', 'statusPath', 'expectedValue', 'mailTestUrl', 'logDownloadUrl', 'requestLogUrl', 'sshAlias'}
        if node.tag != 'app' or len(node) or set(node.attrib) - allowed:
            raise ValueError('config.xml: expected <app> with supported attributes')
        item = dict(node.attrib)
        if not item.get('id') or item['id'] in ids or not item.get('name'):
            raise ValueError('config.xml: each app requires a unique id and a name')
        ids.add(item['id'])
        item.setdefault('backend', 'http')
        if item['backend'] not in ['laravel', 'http', 'json']:
            raise ValueError('config.xml: backend must be laravel, http or json')
        if item.get('sshAlias') and not ALIAS.fullmatch(item['sshAlias']):
            raise ValueError('Invalid SSH alias')
        if not item.get('siteUrl') and not item.get('healthUrl') and not item.get('sshAlias'):
            raise ValueError('config.xml: app needs siteUrl, healthUrl or sshAlias')
        if item['backend'] != 'laravel' and (item.get('mailHealthUrl') or item.get('diagnosticsUrl')):
            raise ValueError('config.xml: Laravel diagnostics require backend="laravel"')
        for key in ['siteUrl', 'healthUrl', 'mailHealthUrl', 'diagnosticsUrl', 'mailTestUrl', 'logDownloadUrl', 'requestLogUrl']:
            if not item.get(key):
                continue
            url = urlsplit(item[key])
            if url.scheme not in ['http', 'https'] or not url.hostname or url.username or url.password or url.fragment:
                raise ValueError(f'config.xml: {key} must be an HTTP/HTTPS URL without credentials or fragment')
            _ = url.port
        apps.append(item)
    if not apps and not allow_empty:
        raise ValueError('config.xml: configure at least one app')
    return {'internet_probes': root.get('internetProbes', '1.1.1.1:443,8.8.8.8:53').split(','), 'apps': apps, 'interval_seconds': interval, 'local_metrics': root.get('localMetrics') == 'true', 'disk_path': root.get('diskPath', 'C:\\')}


def result(status, summary, **details):
    return {'status': status, 'summary': summary, **details}


def ssl_check(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https':
        return result('unknown', 'Not applicable · HTTP URL')
    try:
        context = ssl.create_default_context()
        with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=5) as sock:
            with context.wrap_socket(sock, server_hostname=parsed.hostname) as secure:
                cert = secure.getpeercert()
        expiry = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert['notAfter']), timezone.utc)
        days = math.floor((expiry - datetime.now(timezone.utc)).total_seconds() / 86400)
        status = 'critical' if days < 5 else 'warning' if days < 15 else 'ok'
        return result(status, f'{days} days remaining', expires_at=expiry.isoformat())
    except ssl.SSLCertVerificationError:
        return result('critical', 'Certificate verification failed')
    except (OSError, ValueError, KeyError):
        return result('unknown', 'Certificate could not be checked')


async def website_check(client, url):
    start = time.perf_counter()
    try:
        response = await client.get(url)
        ms = round((time.perf_counter() - start) * 1000)
        status = 'critical' if not response.is_success or ms >= 5000 else 'warning' if ms >= 2000 else 'ok'
        return result(status, f'HTTP {response.status_code} · {ms} ms', duration_ms=ms)
    except httpx.HTTPError:
        return result('critical', 'Website did not respond successfully')


def latency_result(value):
    if type(value) not in [int, float] or not math.isfinite(value) or value < 0:
        return result('unknown', 'Database timing not available')
    return result('critical' if value >= 2000 else 'warning' if value >= 800 else 'ok', f'{value} ms · connection + SELECT 1', duration_ms=value)


async def internet_check(probes):
    async def probe(target):
        writer = None
        try:
            host, port = target.strip().rsplit(':', 1)
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), 2)
            return True
        except (OSError, ValueError, asyncio.TimeoutError):
            return False
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
    outcomes = await asyncio.gather(*(probe(target) for target in probes))
    return result('ok' if any(outcomes) else 'offline', 'Internet reachable' if any(outcomes) else 'All configured internet probes failed')


async def api_check(client, url):
    start = time.perf_counter()
    try:
        response = await client.get(url)
        ms = round((time.perf_counter() - start) * 1000)
        data = response.json()
        checks = data.get('checks', {})
        if data.get('status') not in ['ok', 'fail'] or checks.get('database') not in ['ok', 'fail']:
            raise ValueError('Invalid health response')
        status = 'critical' if response.status_code != 200 or data['status'] != 'ok' else 'warning' if ms >= 800 else 'ok'
        if ms >= 2000:
            status = 'critical'
        return {
            'api': result(status, f'HTTP {response.status_code} · {ms} ms', duration_ms=ms),
            'database_latency': latency_result(data.get('database_duration_ms')),
            'database': result('ok' if checks['database'] == 'ok' else 'critical', 'Connected' if checks['database'] == 'ok' else 'Connection failed', details=str(data.get('database_details', ''))[:300]),
        }
    except (httpx.HTTPError, ValueError, AttributeError):
        return {'api': result('critical', 'Health endpoint unavailable or invalid'), 'database': result('unknown', 'No health data · database status unconfirmed')}


async def mail_check(client, url):
    if not url:
        return result('unknown', 'Mail check not configured in XML')
    try:
        response = await client.get(url)
        data = response.json()
        if response.status_code != 200 or data.get('status') not in ['ok', 'critical', 'unknown']:
            raise ValueError('Invalid mail health response')
        summaries = {'ok': 'SMTP login successful · no email sent', 'critical': 'SMTP connection or authentication failed', 'unknown': 'SMTP login not configured or unsupported'}
        return result(data['status'], summaries[data['status']], details=str(data.get('summary', ''))[:300])
    except (httpx.HTTPError, ValueError, AttributeError):
        return result('unknown', 'Mail health endpoint unavailable')


DIAGNOSTICS = {'cache': 'Laravel cache', 'storage': 'Storage writable', 'sessions': 'Session folder writable', 'compiled_views': 'Compiled views writable', 'bootstrap_cache': 'Bootstrap cache writable', 'queue': 'Queue pending', 'failed_jobs': 'Failed jobs · 24 hours', 'errors_today': 'Laravel errors today'}


async def diagnostics_check(client, url):
    checks = {}
    if url:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get('checks'), dict):
                    checks = data['checks']
        except (httpx.HTTPError, ValueError):
            pass
    results = {}
    for key, label in DIAGNOSTICS.items():
        check = checks.get(key, {})
        if not isinstance(check, dict):
            check = {}
        status = check.get('status', 'unknown')
        if status not in ['ok', 'warning', 'critical', 'unknown']:
            status = 'unknown'
        summary = {'ok': 'Working', 'warning': 'Needs attention', 'critical': 'Check failed', 'unknown': 'Not configured, unsupported or unavailable'}[status]
        value = check.get('value')
        if type(value) is int and value >= 0:
            summary = f'{value}' + (' or more · partial log scan' if check.get('partial') else '')
        results[label] = result(status, summary)
    return results


def local_checks(enabled, path):
    if not enabled:
        return {}
    checks = {}
    for label, read, warn, critical in [
        ('Watcher computer · CPU', lambda: psutil.cpu_percent(interval=0.5), 75, 90),
        ('Watcher computer · RAM', lambda: psutil.virtual_memory().percent, 80, 92),
        ('Watcher computer · Disk', lambda: psutil.disk_usage(path).percent, 80, 90),
    ]:
        try:
            value = read()
            checks[label] = result('critical' if value >= critical else 'warning' if value >= warn else 'ok', f'{value:.1f}% used')
        except (OSError, ValueError):
            checks[label] = result('unknown', 'Local metric unavailable')
    try:
        seconds = max(0, int(time.time() - psutil.boot_time()))
        checks['Watcher computer · Uptime'] = result('ok', f'{seconds // 86400} days · {seconds % 86400 // 3600} hours')
    except OSError:
        checks['Watcher computer · Uptime'] = result('unknown', 'Uptime unavailable')
    try:
        disk = psutil.disk_usage(path)
        checks['Watcher computer · Free disk space'] = result('critical' if disk.percent >= 90 else 'warning' if disk.percent >= 80 else 'ok', f'{disk.free / 1024**3:.1f} GB free of {disk.total / 1024**3:.1f} GB')
    except (OSError, ValueError):
        checks['Watcher computer · Free disk space'] = result('unknown', 'Disk unavailable')
    return checks


CONFIG_PATH = Path(__file__).resolve().parents[1] / 'config.xml'
SETTINGS_PATH = CONFIG_PATH
LEGACY_SETTINGS_PATH = CONFIG_PATH.with_name('settings.json')
app = FastAPI(docs_url=None, redoc_url=None)


CHECK_LABELS = ['Website', 'Website SSL', 'Backend API', 'API SSL', 'Database', 'Database response time', 'Mail', 'Test email', 'Log download', 'Request log', *DIAGNOSTICS.values()]
DEFAULT_DASHBOARD = {'refreshSeconds': 0, 'tableView': False, 'issuesOnly': False, 'showCharts': True, 'notifications': True}

def validate_settings(data):
    if not isinstance(data, dict) or not {'version', 'dashboard', 'apps', 'localMetrics'} <= set(data) or set(data) - {'version', 'dashboard', 'apps', 'localMetrics', 'servers'} or data['version'] != 1:
        raise ValueError('Unsupported settings format')
    dashboard = data['dashboard']
    if not isinstance(dashboard, dict) or set(dashboard) != set(DEFAULT_DASHBOARD):
        raise ValueError('Dashboard preferences are incomplete')
    seconds = dashboard['refreshSeconds']
    if type(seconds) is not int or (seconds != 0 and not 10 <= seconds <= 86400):
        raise ValueError('Refresh interval must be 0 (manual) or 10–86400 seconds')
    if any(type(dashboard[k]) is not bool for k in DEFAULT_DASHBOARD if k != 'refreshSeconds') or type(data['localMetrics']) is not bool:
        raise ValueError('Switch values must be true or false')
    if not isinstance(data['apps'], list) or len(data['apps']) > 100:
        raise ValueError('Configure up to 100 applications')
    servers = data.setdefault('servers', [])
    if not isinstance(servers, list) or len(servers) > 50:
        raise ValueError('Configure up to 50 servers')
    server_ids = set()
    for server in servers:
        validate_server(server)
        if server['id'] in server_ids:
            raise ValueError('Server ids must be unique')
        server_ids.add(server['id'])
    root = Element('monitor', version='1', intervalSeconds='30')
    for item in data['apps']:
        if not isinstance(item, dict) or type(item.get('enabled')) is not bool or not isinstance(item.get('disabledChecks'), list):
            raise ValueError('Each application needs enabled and disabledChecks settings')
        if any(label not in CHECK_LABELS for label in item['disabledChecks']):
            raise ValueError('Unknown check name')
        if item.get('environment', 'unassigned') not in ['testing', 'uat', 'production', 'unassigned']:
            raise ValueError('Environment must be testing, uat or production')
        if not isinstance(item.get('brand', ''), str) or len(item.get('brand', '')) > 100:
            raise ValueError('Brand must be text, at most 100 characters')
        if item.get('serverId', '') not in ['', '__watcher__', *server_ids]:
            raise ValueError('Application references an unknown server')
        attributes = {k: v for k, v in item.items() if k not in ['enabled', 'disabledChecks', 'brand', 'environment', 'serverId']}
        if any(not isinstance(v, str) or len(v) > 2048 for v in attributes.values()):
            raise ValueError('Application fields must be text, at most 2048 characters')
        if attributes.get('id') == '__watcher__':
            raise ValueError('Reserved application id')
        SubElement(root, 'app', attributes)
    if data['apps']:
        load_config(io.BytesIO(tostring(root)))
    return data

def effective_config(settings):
    return {**config, 'apps': settings['apps'], 'local_metrics': settings['localMetrics'], 'servers': settings.get('servers', [])}

def xml_bool(value):
    if value not in ('true', 'false'):
        raise ValueError('XML boolean values must be true or false')
    return value == 'true'


def read_settings_xml(path):
    root = ElementTree.parse(path).getroot()
    base = Element(root.tag, root.attrib)
    apps = []
    servers = []
    dashboard = dict(DEFAULT_DASHBOARD)
    seen_dashboard = False
    for node in root:
        values = dict(node.attrib)
        if node.tag == 'dashboard' and not seen_dashboard and not len(node):
            seen_dashboard = True
            if values.keys() - dashboard.keys():
                raise ValueError('Unsupported dashboard setting')
            dashboard.update({key: int(value) if key == 'refreshSeconds' else xml_bool(value)
                              for key, value in values.items()})
        elif node.tag == 'server' and not len(node):
            values['enabled'] = xml_bool(values.get('enabled', 'true'))
            servers.append(values)
        elif node.tag == 'app':
            enabled = xml_bool(values.pop('enabled', 'true'))
            metadata = {key: values.pop(key) for key in ('brand', 'environment', 'serverId') if key in values}
            disabled = []
            for child in node:
                if child.tag != 'disabledCheck' or len(child) or set(child.attrib) != {'name'}:
                    raise ValueError('Expected <disabledCheck name="..."/>')
                disabled.append(child.attrib['name'])
            SubElement(base, 'app', values)
            apps.append({**values, **metadata, 'enabled': enabled, 'disabledChecks': disabled})
        else:
            raise ValueError(f'Unexpected config.xml element: {node.tag}')
    base_config = load_config(io.BytesIO(tostring(base)), allow_empty=True)
    for entry in apps:
        entry.setdefault('backend', 'http')
    data = validate_settings({'version': 1, 'dashboard': dashboard, 'apps': apps,
                              'localMetrics': base_config['local_metrics'], 'servers': servers})
    return base_config, data, seen_dashboard


SERVER_XML_EXAMPLE = """
  To configure an Ubuntu metrics agent, add this element and fill in its URL and token.
  <server id="ubuntu-prod" name="Ubuntu production" kind="remote" os="ubuntu"
          agentUrl="http://127.0.0.1:18449/v1/metrics" token="" enabled="false"/>
  The example URL uses an SSH tunnel. Set enabled="true" when the agent is reachable.
  Link an application by adding serverId="ubuntu-prod" to its app element.
  """


def write_settings_xml(path, data, base_config):
    def attributes(values):
        return {key: str(value).lower() if isinstance(value, bool) else str(value)
                for key, value in values.items()}

    root = Element('monitor', attributes({
        'version': 1, 'intervalSeconds': base_config['interval_seconds'],
        'localMetrics': data['localMetrics'], 'diskPath': base_config['disk_path'],
        'internetProbes': ','.join(base_config['internet_probes']),
    }))
    root.append(Comment(' Dashboard preferences. Set refreshSeconds="0" for manual refresh. '))
    SubElement(root, 'dashboard', attributes(data['dashboard']))
    root.append(Comment(
        ' Applications. The brand groups entries in the dashboard. '
        'Set environment to production, uat, testing or unassigned. '
        'Replace placeholder URLs before setting enabled="true". '
        'Use sshAlias for direct diagnostics over SSH. '
    ))
    for application in data['apps']:
        environment = application.get('environment', 'unassigned')
        root.append(Comment(f' Application environment: {environment.capitalize()}. '))
        node = SubElement(root, 'app', attributes({key: value for key, value in application.items()
                                                   if key != 'disabledChecks'}))
        for label in application['disabledChecks']:
            SubElement(node, 'disabledCheck', name=label)
    root.append(Comment(
        ' Server metrics agents. Set agentUrl and token before enabling. '
        'Link an application using serverId with the matching server id. '
    ))
    for server in data['servers']:
        SubElement(root, 'server', attributes(server))
    if not data["servers"]:
        root.append(Comment(SERVER_XML_EXAMPLE))
    indent(root)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, delete=False) as handle:
            temporary = handle.name
            handle.write(tostring(root, encoding='utf-8', xml_declaration=True))
            handle.write(b'\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


config, settings, xml_settings_present = read_settings_xml(CONFIG_PATH)
if not xml_settings_present:
    if LEGACY_SETTINGS_PATH.exists():
        settings = validate_settings(json.loads(LEGACY_SETTINGS_PATH.read_text(encoding='utf-8-sig')))
    write_settings_xml(CONFIG_PATH, settings, config)
config = effective_config(settings)

@app.get('/api/settings')
def get_settings():
    return public_settings(settings)

def public_settings(value):
    return {**value, 'servers': clean_servers(value.get('servers', []))}

def resolve_server_tokens(candidate):
    if not isinstance(candidate, dict):
        raise ValueError('Settings must be an object')
    previous = {s['id']: s for s in settings.get('servers', [])}
    servers = candidate.get('servers', [])
    if isinstance(servers, list):
        for server in servers:
            if isinstance(server, dict):
                server.pop('hasToken', None)
                if not server.get('token') and server.get('id') in previous:
                    server['token'] = previous[server['id']].get('token', '')
    return candidate

@app.post('/api/servers/test')
async def test_server(request: Request):
    if request.headers.get('x-monitor-action') != 'manual' or request.headers.get('origin') not in [None, 'http://127.0.0.1:5173', 'http://localhost:5173']:
        raise HTTPException(403, 'Local manual action required')
    if len(await request.body()) > 16384:
        raise HTTPException(413, 'Request too large')
    try:
        server = await request.json()
        candidate = resolve_server_tokens({'servers': [server]})['servers'][0]
        validate_server(candidate)
        candidate = {**candidate, 'enabled': True}
        validate_server(candidate)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HTTPException(422, str(exc))
    return await poll_server(candidate)

@app.put('/api/settings')
async def put_settings(request: Request):
    global settings, config
    if request.headers.get('x-monitor-action') != 'manual' or request.headers.get('origin') not in [None, 'http://127.0.0.1:5173', 'http://localhost:5173']:
        raise HTTPException(403, 'Local manual action required')
    if len(await request.body()) > 512000:
        raise HTTPException(413, 'Settings too large')
    try:
        candidate = validate_settings(resolve_server_tokens(await request.json()))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc))
    try:
        write_settings_xml(SETTINGS_PATH, candidate, config)
    except OSError:
        raise HTTPException(500, 'Could not save config.xml; previous settings retained')
    config = effective_config(candidate)
    settings = candidate
    return public_settings(settings)


async def generic_api_check(client, item):
    if item['backend'] == 'http':
        return await website_check(client, item['healthUrl'])
    started = time.perf_counter()
    try:
        response = await client.get(item['healthUrl'])
        data = response.json()
        for part in item.get('statusPath', 'status').split('.'):
            data = data[part]
        ok = response.is_success and str(data) == item.get('expectedValue', 'ok')
        ms = round((time.perf_counter() - started) * 1000)
        return result('ok' if ok else 'critical', f'HTTP {response.status_code} · {ms} ms · ' + ('Healthy' if ok else 'Health condition failed'))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return result('unknown', 'JSON health endpoint unavailable or unexpected format')


async def direct_checks(item, labels):
    try:
        values = await direct_request(item, 'checks', labels=labels)
    except (OSError, ValueError):
        values = {}
    return {label: values.get(label, result('unknown', 'SSH check unavailable')) for label in labels}


async def check_application(client, item):
    checks = {}
    enabled = lambda label: label not in item.get('disabledChecks', [])
    if item.get('siteUrl'):
        if enabled('Website'):
            checks['Website'] = await website_check(client, item['siteUrl'])
        if enabled('Website SSL'):
            checks['Website SSL'] = await asyncio.to_thread(ssl_check, item['siteUrl'])
    direct = bool(item.get('sshAlias'))
    if direct:
        labels = [label for label in DIRECT_LABELS if enabled(label)]
        if labels:
            checks.update(await direct_checks(item, labels))
    if item.get('healthUrl') and not direct:
        if item['backend'] == 'laravel':
            labels = {'Backend API': 'api', 'Database': 'database', 'Database response time': 'database_latency'}
            if any(enabled(label) for label in labels):
                health = await api_check(client, item['healthUrl'])
                checks.update({label: health[key] for label, key in labels.items() if enabled(label) and key in health})
        elif enabled('Backend API'):
            checks['Backend API'] = await generic_api_check(client, item)
        if enabled('API SSL'):
            checks['API SSL'] = await asyncio.to_thread(ssl_check, item['healthUrl'])
    if not direct and item.get('mailHealthUrl') and enabled('Mail'):
        checks['Mail'] = await mail_check(client, item['mailHealthUrl'])
    if not direct and item.get('diagnosticsUrl') and any(enabled(label) for label in DIAGNOSTICS.values()):
        checks.update({label: value for label, value in (await diagnostics_check(client, item['diagnosticsUrl'])).items() if enabled(label)})
    meaningful = [check['status'] for name, check in checks.items() if 'SSL' not in name or check['status'] != 'unknown']
    status = next((value for value in ['critical', 'warning', 'unknown'] if value in meaningful), 'ok' if checks else 'unknown')
    return {'id': item['id'], 'name': item['name'], 'backend': item['backend'], 'brand': item.get('brand') or item['name'], 'environment': item.get('environment', 'unassigned'), 'server_id': item.get('serverId', ''), 'site_url': item.get('siteUrl'), 'health_url': item.get('healthUrl'), 'status': status, 'checks': checks, 'actions': {'mail': (direct or bool(item.get('mailTestUrl'))) and enabled('Mail') and enabled('Test email'), 'logs': (direct or bool(item.get('logDownloadUrl'))) and enabled('Laravel errors today') and enabled('Log download'), 'analysis': (direct or bool(item.get('logDownloadUrl'))) and enabled('Laravel errors today') and enabled('Log download')}}


@app.get('/api/live')
async def live():
    cfg = config
    internet = await internet_check(cfg['internet_probes'])
    async with httpx.AsyncClient(timeout=8, follow_redirects=True, trust_env=False) as client:
        apps, local, servers = await asyncio.gather(
            asyncio.gather(*(check_application(client, item) for item in cfg['apps'] if item.get('enabled', True))),
            asyncio.to_thread(local_checks, cfg['local_metrics'], cfg['disk_path']),
            asyncio.gather(*(poll_server(server) for server in cfg.get('servers', []))),
        )
    local['Watcher internet'] = internet
    if internet['status'] == 'offline':
        for item in apps:
            source = next(a for a in cfg['apps'] if a['id'] == item['id'])
            for label in item['checks']:
                if source.get('sshAlias') and label in DIRECT_LABELS:
                    continue
                url_key = 'siteUrl' if label.startswith('Website') else 'mailHealthUrl' if label == 'Mail' else 'diagnosticsUrl' if label in DIAGNOSTICS.values() else 'healthUrl'
                host = urlsplit(source.get(url_key, '')).hostname
                if host and host not in ['localhost', '127.0.0.1', '::1']:
                    item['checks'][label] = result('offline', 'Watcher offline · remote result unconfirmed')
            item['status'] = next((v for v in ['critical', 'warning', 'offline', 'unknown'] if any(c['status'] == v for c in item['checks'].values())), 'ok')
    counts = {status: sum(check['status'] == status for item in apps for check in item['checks'].values()) for status in ['ok', 'warning', 'critical', 'unknown', 'offline']}
    return {'checked_at': datetime.now(timezone.utc).isoformat(), 'apps': apps, 'watcher': local, 'servers': servers, 'counts': counts, 'configured_apps': [{k: v for k, v in item.items() if k in ['id', 'name', 'brand', 'environment', 'enabled', 'disabledChecks', 'siteUrl', 'healthUrl', 'mailHealthUrl', 'diagnosticsUrl', 'backend', 'serverId', 'sshAlias']} for item in cfg['apps']]}


@app.post('/api/apps/{app_id}/mail-test')
async def manual_mail(app_id: str, request: Request):
    if request.headers.get('x-monitor-action') != 'manual' or request.headers.get('origin') not in [None, 'http://127.0.0.1:5173', 'http://localhost:5173']:
        raise HTTPException(403, 'Manual action header and local origin required')
    item = next((a for a in config['apps'] if a['id'] == app_id), None)
    if not item or not item.get('enabled', True) or any(label in item.get('disabledChecks', []) for label in ('Mail', 'Test email')) or not (item.get('mailTestUrl') or item.get('sshAlias')):
        raise HTTPException(404, 'Mail action not configured in XML')
    body = await request.json()
    email = body.get('email', '')
    if not isinstance(email, str) or len(email) > 254 or '@' not in email or any(c in email for c in '\r\n'):
        raise HTTPException(422, 'Enter a valid recipient email')
    if item.get('sshAlias'):
        try:
            return await direct_request(item, 'mail', recipient=email)
        except (OSError, ValueError):
            raise HTTPException(502, 'Direct SMTP test failed. Check SSH and SMTP configuration.')
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            response = await client.post(item['mailTestUrl'], json={'email': email}, headers={'X-Monitor-Action': 'manual', 'Accept': 'application/json'})
        if response.status_code == 422:
            raise HTTPException(422, 'Enter a valid recipient email')
        if response.status_code == 429:
            raise HTTPException(429, 'Too many mail tests; wait a minute')
        if response.status_code != 200:
            raise HTTPException(502, 'Mail test endpoint unavailable')
        data = response.json()
        return {'status': data.get('status', 'unknown'), 'summary': str(data.get('summary', 'No result'))[:300]}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'Mail test timed out or returned an invalid response')


@app.get('/api/apps/{app_id}/logs-today')
async def download_logs(app_id: str):
    item = next((a for a in config['apps'] if a['id'] == app_id), None)
    if not item or not item.get('enabled', True) or any(label in item.get('disabledChecks', []) for label in ('Laravel errors today', 'Log download')) or not (item.get('logDownloadUrl') or item.get('sshAlias')):
        raise HTTPException(404, 'Log download not configured in XML')
    if item.get('sshAlias'):
        from backend.log_analysis import analyse_errors
        sources = await direct_logs(item, include_requests=False)
        report = await asyncio.to_thread(analyse_errors, sources.get('logs', ''))
        lines = [f"{group['count']} x {group['message']}" for group in report['groups']]
        return Response('\n'.join(lines), media_type='text/plain', headers={
            'Content-Disposition': 'attachment; filename="today-laravel-errors.txt"',
            'Cache-Control': 'no-store',
        })
    try:
        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            async with client.stream('GET', item['logDownloadUrl']) as response:
                if response.status_code != 200:
                    raise HTTPException(502, 'Log export unavailable')
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 21*1024*1024:
                        raise HTTPException(502, 'Log export exceeds size limit')
        return Response(bytes(chunks), media_type='text/plain', headers={'Content-Disposition': 'attachment; filename="today-laravel.log"', 'Cache-Control': 'no-store'})
    except httpx.HTTPError:
        raise HTTPException(502, 'Log export unavailable')

@app.post('/api/recheck')
async def recheck(request: Request):
    if request.headers.get('x-monitor-action') != 'manual' or request.headers.get('origin') not in [None, 'http://127.0.0.1:5173', 'http://localhost:5173']:
        raise HTTPException(403, 'Local manual action required')
    body = await request.json()
    app_id, label = body.get('app_id'), body.get('check')
    if not isinstance(label, str):
        raise HTTPException(422, 'Check name required')
    if app_id == '__watcher__':
        if label == 'Watcher internet':
            value = await internet_check(config['internet_probes'])
        else:
            values = await asyncio.to_thread(local_checks, config['local_metrics'], config['disk_path'])
            if label not in values:
                raise HTTPException(404, 'Check unavailable')
            value = values[label]
    else:
        item = next((a for a in config['apps'] if a['id'] == app_id), None)
        if not item or not item.get('enabled', True) or label in item.get('disabledChecks', []):
            raise HTTPException(404, 'Application or check disabled or unavailable')
        if item.get('sshAlias') and not label.startswith('Website'):
            if label not in DIRECT_LABELS:
                raise HTTPException(404, 'Direct check not configured')
            values = await direct_checks(item, [label])
            return {'app_id': app_id, 'check': label, 'result': values[label],
                    'checked_at': datetime.now(timezone.utc).isoformat()}
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, trust_env=False) as client:
            if label == 'Website' and item.get('siteUrl'):
                value = await website_check(client, item['siteUrl'])
            elif label in ['Website SSL', 'API SSL'] and item.get('siteUrl' if label == 'Website SSL' else 'healthUrl'):
                value = await asyncio.to_thread(ssl_check, item['siteUrl' if label == 'Website SSL' else 'healthUrl'])
            elif label in ['Backend API', 'Database', 'Database response time'] and item.get('healthUrl'):
                if item['backend'] == 'laravel':
                    health = await api_check(client, item['healthUrl'])
                    value = health.get({'Backend API':'api', 'Database':'database', 'Database response time':'database_latency'}[label], result('unknown','Timing unavailable'))
                elif label == 'Backend API':
                    value = await generic_api_check(client, item)
                else:
                    raise HTTPException(404, 'Database probe not configured')
            elif label == 'Mail' and item.get('mailHealthUrl'):
                value = await mail_check(client, item['mailHealthUrl'])
            elif label in DIAGNOSTICS.values() and item.get('diagnosticsUrl'):
                value = (await diagnostics_check(client, item['diagnosticsUrl']))[label]
            else:
                raise HTTPException(404, 'Check not configured')
    return {'app_id': app_id, 'check': label, 'result': value, 'checked_at': datetime.now(timezone.utc).isoformat()}


async def direct_logs(item, include_requests):
    try:
        return await direct_request(item, 'logs', includeRequests=include_requests)
    except (OSError, ValueError):
        raise HTTPException(502, 'SSH logs unavailable. Check the remote configuration and permissions.')


@app.post('/api/apps/{app_id}/analyse-logs')
async def analyse_logs(app_id: str, request: Request):
    from backend.log_analysis import analyse_errors, analyse_requests
    if request.headers.get('x-monitor-action') != 'manual' or request.headers.get('origin') not in [None, 'http://127.0.0.1:5173', 'http://localhost:5173']:
        raise HTTPException(403, 'Local manual action required')
    item = next((a for a in config['apps'] if a['id'] == app_id), None)
    if not item or not item.get('enabled', True) or any(label in item.get('disabledChecks', []) for label in ('Laravel errors today', 'Log download')) or not (item.get('logDownloadUrl') or item.get('sshAlias')):
        raise HTTPException(404, 'Log source not configured in XML')
    if item.get('sshAlias'):
        sources = await direct_logs(item, include_requests='Request log' not in item.get('disabledChecks', []))
        errors, requests = sources.get('logs', ''), sources.get('requests', '')
        report = await asyncio.to_thread(lambda: {'errors': analyse_errors(errors), 'requests': analyse_requests(requests)})
        return {**report, 'name': item['name'], 'generated_at': datetime.now(timezone.utc).isoformat(),
                'sources': {'errors': 'Read directly over SSH', 'requests': 'Read over SSH' if requests else 'No timing records'},
                'limitations': ['Reads bounded log tails. Request timing needs an existing compatible JSONL file.']}
    async def read_source(client, url, limit):
        if not url:
            return '', 'Not configured'
        try:
            async with client.stream('GET', url) as response:
                if response.status_code != 200:
                    return '', 'Source unavailable'
                content = bytearray()
                async for part in response.aiter_bytes():
                    if len(content) + len(part) > limit:
                        return '', 'Source exceeds analysis size limit'
                    content.extend(part)
                return content.decode('utf-8', errors='replace'), 'Read successfully'
        except httpx.HTTPError:
            return '', 'Source request failed or timed out'
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        (errors, error_status), (requests, request_status) = await asyncio.gather(
            read_source(client,item['logDownloadUrl'],21*1024*1024),
            read_source(client, None if 'Request log' in item.get('disabledChecks', []) else item.get('requestLogUrl'),11*1024*1024))
    report = await asyncio.to_thread(lambda: {'errors':analyse_errors(errors), 'requests':analyse_requests(requests)})
    return {**report, 'name':item['name'], 'generated_at':datetime.now(timezone.utc).isoformat(), 'sources':{'errors':error_status, 'requests':request_status}, 'limitations':['Error source contains today’s entries from a bounded tail of standard Laravel logs. Earlier entries may be outside that tail.', 'Grouping uses sanitized message patterns; related errors can merge and distinct groups may share a cause.', 'Locations are shown only when an application PHP frame was recorded. No source code is changed.', 'The analysis creates no log copy on disk. Laravel original logs and its new local API timing source remain on the app.']}
