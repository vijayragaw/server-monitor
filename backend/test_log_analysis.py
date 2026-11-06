from backend.log_analysis import analyse_errors, analyse_requests, sanitize


def test_groups_repeated_errors_and_finds_application_location():
    report = analyse_errors('''[2026-11-02 09:00:00] local.ERROR: SQLSTATE connection timed out for record 12
#0 C:/project/app/Http/Controllers/InvoiceController.php(142): run()
[2026-11-02 09:01:00] local.ERROR: SQLSTATE connection timed out for record 13
''')
    assert report['total_occurrences'] == 2
    assert report['unique_errors'] == 1
    group = report['groups'][0]
    assert group['category'] == 'database'
    assert group['location'] == 'app/Http/Controllers/InvoiceController.php:142'
    assert group['first_seen'] != group['last_seen']


def test_sanitizes_known_sensitive_patterns():
    value = sanitize('password=secret123 bearer ABCDEF user@example.com https://host/path?token=x')
    for secret in ['secret123', 'ABCDEF', 'user@example.com', 'token=x']:
        assert secret not in value


def test_non_error_headers_do_not_count():
    assert analyse_errors('[2026-11-02 09:00:00] local.INFO: Fine')['total_occurrences'] == 0


def test_request_counts_do_not_claim_duplicates():
    import json
    rows = [dict(at='2026-11-02T09:00:00+05:30', time=t, method='GET', route='api/invoices/{id}', status=status, duration_ms=ms) for t,status,ms in [(100,200,50),(100.5,500,2500),(104,422,100)]]
    report = analyse_requests('\n'.join(map(json.dumps, rows))+'\ninvalid')
    group = report['routes'][0]
    assert report['total_requests'] == 3
    assert group['burst_pairs'] == 1
    assert group['failures_5xx'] == 1
    assert group['responses_4xx'] == 1
    assert group['slow_requests'] == 1
    assert report['invalid_lines'] == 1
    assert 'do not prove' in report['note']
