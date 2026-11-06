"""Executed with Python 3 on the monitored host over SSH."""
import datetime
import json
import os
import re
import smtplib
import ssl
import subprocess
import time
from email.message import EmailMessage
from pathlib import Path
from xml.etree import ElementTree


def check(status, summary, **details):
    return dict(status=status, summary=summary, **details)


def mysql(options, statement):
    return subprocess.check_output(
        ['mysql', '--defaults-file=' + str(Path(options).expanduser()),
         '--batch', '--skip-column-names', '--connect-timeout=4', '-e', statement],
        stderr=subprocess.DEVNULL, timeout=6, text=True,
    ).strip()


def smtp(options, recipient=None):
    context = ssl.create_default_context()
    host = options['host']
    port = options.get('port', 587)
    if options.get('tls') == 'implicit':
        connection = smtplib.SMTP_SSL(host, port, timeout=5, context=context)
    else:
        connection = smtplib.SMTP(host, port, timeout=5)
    with connection:
        if options.get('tls') != 'implicit':
            connection.starttls(context=context)
        if options.get('username'):
            connection.login(options['username'], options['password'])
        if recipient:
            message = EmailMessage()
            message['From'] = options['from']
            message['To'] = recipient
            message['Subject'] = 'Server Monitor test'
            message.set_content('This is a manually requested SMTP test.')
            connection.send_message(message)
    return check('ok', 'Test email sent' if recipient else 'SMTP connection verified')


def tail(path, limit):
    if not path.is_file():
        return ''
    with path.open('rb') as source:
        size = source.seek(0, 2)
        source.seek(max(size - limit, 0))
        if size > limit:
            source.readline()
        return source.read(limit).decode('utf-8', errors='replace')


def today_logs(folder):
    today = datetime.date.today().isoformat()
    lines = []
    for name in ['laravel.log', f'laravel-{today}.log']:
        if not (folder / name).is_file():
            continue
        current = False
        for line in tail(folder / name, 1024 * 1024).splitlines():
            if re.match(r'^\[\d{4}-\d\d-\d\d ', line):
                current = line.startswith('[' + today + ' ')
            if current:
                lines.append(line)
    return '\n'.join(lines)


def collect(options, labels):
    values = {}
    database = options.get('mysqlDefaultsFile')
    if database and {'Database', 'Database response time'} & labels:
        started = time.monotonic()
        try:
            if mysql(database, 'SELECT 1') != '1':
                raise ValueError('Unexpected response')
            ms = round((time.monotonic() - started) * 1000)
            values['Database'] = check('ok', 'MySQL connection verified')
            values['Database response time'] = check(
                'critical' if ms >= 2000 else 'warning' if ms >= 800 else 'ok',
                f'{ms} ms including client startup', duration_ms=ms)
        except (OSError, ValueError, subprocess.SubprocessError):
            values['Database'] = check('critical', 'MySQL connection or SELECT 1 failed')
            values['Database response time'] = check('unknown', 'Database timing unavailable')
    if options.get('smtp') and 'Mail' in labels:
        try:
            values['Mail'] = smtp(options['smtp'])
        except (OSError, ValueError, KeyError):
            values['Mail'] = check('critical', 'SMTP connection or authentication failed')
    if options.get('logDir') and 'Laravel errors today' in labels:
        folder = Path(options['logDir'])
        try:
            today = datetime.date.today().isoformat()
            if not any((folder / name).is_file() for name in ['laravel.log', f'laravel-{today}.log']):
                raise OSError('Log file unavailable')
            count = len(re.findall(r'^\[[^\]]+\]\s+\w+\.(ERROR|CRITICAL|ALERT|EMERGENCY):', today_logs(folder), re.M))
            values['Laravel errors today'] = check(
                'critical' if count >= 50 else 'warning' if count >= 10 else 'ok',
                f'{count} errors in the recent log tail')
        except OSError:
            values['Laravel errors today'] = check('unknown', 'Laravel logs are unavailable')
    return {label: values.get(label, check('unknown', 'Direct source not configured')) for label in labels}


def run(request):
    folder = Path.home() / '.config/server-monitor'
    xml = folder / 'direct.xml'
    if xml.exists():
        root = ElementTree.parse(xml).getroot()
        if root.tag != 'direct':
            raise ValueError('Expected a direct XML root')
        entries = [app for app in root.findall('app') if app.get('id') == request['app']]
        if len(entries) != 1:
            raise ValueError('Expected one matching application in direct.xml')
        entry = entries[0]
        options = dict(entry.attrib)
        smtp_element = entry.find('smtp')
        if smtp_element is not None:
            options['smtp'] = dict(smtp_element.attrib)
            if 'port' in options['smtp']:
                options['smtp']['port'] = int(options['smtp']['port'])
    else:
        options = json.loads((folder / 'direct.json').read_text(encoding='utf-8'))[request['app']]
    action = request['action']
    if action == 'checks':
        return collect(options, set(request['labels']))
    if action == 'mail':
        return smtp(options['smtp'], request['recipient'])
    if action == 'logs':
        logs = today_logs(Path(options['logDir']))
        requests = tail(Path(options['requestLog']), 1024 * 1024) if request.get('includeRequests') and options.get('requestLog') else ''
        return {'logs': logs, 'requests': requests}
    raise ValueError('Unknown action')
