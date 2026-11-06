"""Bounded, deterministic log analysis. Input and reports stay in memory."""
import re
import json
import math
from collections import defaultdict

RULES = [
    ('database', ('sqlstate', 'mysql', 'pdoexception', 'deadlock'), 'Database operation failed', 'Check connectivity, permissions, connection limits and slow queries.', 'Recheck the database and affected API; confirm no new matching errors appear.'),
    ('mail', ('smtp', 'mailer', 'transportexception', 'swift_transport'), 'Mail transport failed', 'Check the provider response, credentials, app-password policy, TLS and network access.', 'Run the SMTP login check, then optionally send a manual test.'),
    ('permission', ('permission denied', 'not writable', 'failed to open stream'), 'File or folder access failed', 'Check that the folder exists and the PHP process has appropriate access.', 'Recheck storage and repeat the affected request.'),
    ('queue', ('maxattempts', 'queue', 'job failed'), 'Background job failed', 'Inspect worker availability, retry limits and the original job exception.', 'Confirm workers are active and new jobs complete without further failures.'),
    ('timeout', ('timeout', 'timed out'), 'Operation timed out', 'Check the downstream service, network latency and configured timeouts.', 'Repeat the affected request and compare response time.'),
]


def sanitize(text):
    text = re.sub(r'(?i)(password|secret|token|authorization|cookie|api[_-]?key)\s*[:=]\s*\S+', r'\1=[REDACTED]', text)
    text = re.sub(r'(?i)(bearer|basic)\s+\S+', '[AUTH REDACTED]', text)
    text = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email]', text)
    text = re.sub(r'https?://\S+', '[url]', text)
    text = re.sub(r'(["\']).*?\1', '[value]', text)
    text = re.sub(r'\b[A-Za-z0-9_+/=-]{36,}\b', '[identifier]', text)
    return text[:500]


def analyse_errors(text):
    groups = {}
    entry = re.compile(r'^\[(\d{4}-\d{2}-\d{2} [^\]]+)\]\s+\w+\.(ERROR|CRITICAL|ALERT|EMERGENCY):\s*(.*)')
    current = None
    for line in text.splitlines():
        match = entry.match(line)
        if match:
            stamp, level, message = match.groups()
            safe = sanitize(message)
            fingerprint = re.sub(r'\b\d+\b', '#', safe)
            current = groups.setdefault(fingerprint, {'message': safe, 'count': 0, 'first_seen': stamp, 'last_seen': stamp, 'level': level, 'location': None, 'api': 'Not recorded in this error log'})
            current['count'] += 1
            current['first_seen'] = min(current['first_seen'], stamp)
            current['last_seen'] = max(current['last_seen'], stamp)
            lower = message.lower()
            rule = next((r for r in RULES if any(word in lower for word in r[1])), None)
            current.update({'category': rule[0] if rule else 'application', 'meaning': rule[2] if rule else 'Application exception recorded', 'suggested_checks': rule[3] if rule else 'Inspect the reported source line and exception type; reproduce with a safe test request.', 'verify': rule[4] if rule else 'Repeat the affected operation and confirm no new matching errors appear.'})
        elif re.match(r'^\[\d{4}-\d{2}-\d{2}', line):
            current = None
        if current and not current['location']:
            location = re.search(r'((?:app|routes|resources)[/\\][^\s"\'<>]+?\.php)[(:](\d+)', line)
            if location:
                current['location'] = location[1].replace('\\', '/') + ':' + location[2]
    ranked = sorted(groups.values(), key=lambda g: g['count'], reverse=True)
    return {'total_occurrences': sum(g['count'] for g in ranked), 'unique_errors': len(ranked), 'repeated_groups': sum(g['count'] > 1 for g in ranked), 'groups': ranked[:100], 'group_limit': 100}


def analyse_requests(text):
    routes = defaultdict(lambda: {'count': 0, 'total_ms': 0, 'max_ms': 0, 'failures': 0, 'client_errors': 0, 'slow': 0, 'bursts': 0, 'last': None})
    first = last = None
    invalid = total = 0
    for line in text.splitlines():
        try:
            row = json.loads(line)
            route, method = row['route'], row['method']
            ms, stamp, status = float(row['duration_ms']), float(row['time']), int(row['status'])
            if not isinstance(row.get('at'), str) or not math.isfinite(stamp) or not isinstance(route, str) or method not in ['GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'] or not 0 <= ms < 86400000:
                raise ValueError()
            key = method+' '+sanitize(route)
        except (ValueError, KeyError, TypeError):
            invalid += 1
            continue
        group = routes[key]
        group['count'] += 1; total += 1
        group['total_ms'] += ms; group['max_ms'] = max(group['max_ms'], ms)
        group['failures'] += status >= 500; group['client_errors'] += 400 <= status < 500
        group['slow'] += ms >= 2000
        if group['last'] is not None and 0 <= stamp - group['last'] <= 1:
            group['bursts'] += 1
        group['last'] = stamp
        first = row['at'] if first is None else min(first, row['at'])
        last = row['at'] if last is None else max(last, row['at'])
    output = [{'route': key, 'count': g['count'], 'average_ms': round(g['total_ms']/g['count'],1), 'max_ms': round(g['max_ms'],1), 'failures_5xx':g['failures'], 'responses_4xx':g['client_errors'], 'slow_requests':g['slow'], 'burst_pairs':g['bursts']} for key,g in routes.items()]
    return {'total_requests': total, 'coverage_from': first, 'coverage_to':last, 'invalid_lines':invalid, 'routes':sorted(output,key=lambda r:r['count'],reverse=True)[:100], 'note':'Counts cover only requests recorded after instrumentation was enabled. Burst pairs are same-route calls within one second across all callers; they do not prove duplicate requests. Request bodies, users and IP addresses are not collected.'}
