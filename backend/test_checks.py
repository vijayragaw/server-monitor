import asyncio
import ssl
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from defusedxml.common import DefusedXmlException

from backend.app import api_check, load_config, ssl_check, diagnostics_check, local_checks


def test_config_rejects_entity(tmp_path):
    path = tmp_path / 'config.xml'
    path.write_text('<!DOCTYPE monitor [<!ENTITY x "bad">]><monitor>&x;</monitor>')
    with pytest.raises(DefusedXmlException):
        load_config(path)


def test_http_has_no_certificate():
    assert ssl_check('http://localhost:4200')['status'] == 'unknown'


@pytest.mark.parametrize('days,status', [(20, 'ok'), (10, 'warning'), (2, 'critical')])
def test_ssl_expiry(days, status):
    expiry = datetime.now(timezone.utc) + timedelta(days=days, hours=1)

    class Secure:
        def getpeercert(self):
            return {'notAfter': expiry.strftime('%b %d %H:%M:%S %Y GMT')}

    @contextmanager
    def connection(*args, **kwargs):
        yield Secure()

    with patch('backend.app.socket.create_connection', connection), patch('backend.app.ssl.create_default_context') as context:
        context.return_value.wrap_socket.side_effect = connection
        assert ssl_check('https://example.com')['status'] == status


def test_ssl_invalid():
    with patch('backend.app.socket.create_connection', side_effect=ssl.SSLCertVerificationError('invalid')):
        assert ssl_check('https://example.com')['status'] == 'critical'


def test_unreachable_api_does_not_claim_database_failure():
    async def run():
        def handler(request):
            raise httpx.ConnectError('unreachable')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            data = await api_check(client, 'http://localhost/health')
            assert data['api']['status'] == 'critical'
            assert data['database']['status'] == 'unknown'
    asyncio.run(run())


def test_diagnostics_missing_data_is_unknown():
    data = asyncio.run(diagnostics_check(None, None))
    assert data and all(value['status'] == 'unknown' for value in data.values())


def test_local_metrics_disabled():
    assert local_checks(False, 'missing') == {}


def test_local_cpu_threshold_and_bad_disk():
    with patch('backend.app.psutil.cpu_percent', return_value=95), patch('backend.app.psutil.disk_usage', side_effect=OSError):
        data = local_checks(True, 'missing')
    assert data['Watcher computer · CPU']['status'] == 'critical'
    assert data['Watcher computer · Disk']['status'] == 'unknown'

def test_manual_mail_requires_action_header():
    from fastapi.testclient import TestClient
    from backend.app import app
    response = TestClient(app).post('/api/apps/billing-local/mail-test', json={'email': 'person@example.com'})
    assert response.status_code == 403


def test_manual_mail_rejects_invalid_recipient_without_sending():
    from fastapi.testclient import TestClient
    from backend.app import app
    response = TestClient(app).post('/api/apps/billing-local/mail-test', headers={'X-Monitor-Action': 'manual'}, json={'email': 'bad\r\n@example.com'})
    assert response.status_code == 422


def test_manual_mail_rejects_cross_origin():
    from fastapi.testclient import TestClient
    from backend.app import app
    response = TestClient(app).post('/api/apps/billing-local/mail-test', headers={'X-Monitor-Action': 'manual', 'Origin': 'https://example.com'}, json={'email': 'person@example.com'})
    assert response.status_code == 403

@pytest.mark.parametrize('value,status', [(10,'ok'), (800,'warning'), (2000,'critical'), (None,'unknown'), (-1,'unknown')])
def test_database_timing_thresholds(value,status):
    from backend.app import latency_result
    assert latency_result(value)['status'] == status


def test_internet_probe_success_and_failure():
    from backend.app import internet_check
    from unittest.mock import AsyncMock, MagicMock
    writer = MagicMock()
    writer.wait_closed = AsyncMock()
    with patch('backend.app.asyncio.open_connection', new=AsyncMock(return_value=(None,writer))):
        assert asyncio.run(internet_check(['127.0.0.1:443']))['status'] == 'ok'
    with patch('backend.app.asyncio.open_connection', new=AsyncMock(side_effect=OSError)):
        assert asyncio.run(internet_check(['127.0.0.1:443']))['status'] == 'offline'

def test_recheck_website_does_not_run_other_checks():
    from backend.app import app
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    with patch('backend.app.website_check',new=AsyncMock(return_value={'status':'ok','summary':'HTTP 200'})) as website, patch('backend.app.mail_check',new=AsyncMock()) as mail:
        response=TestClient(app).post('/api/recheck',headers={'X-Monitor-Action':'manual'},json={'app_id':'billing-local','check':'Website'})
    assert response.status_code==200
    assert response.json()['result']['status']=='ok'
    website.assert_awaited_once()
    mail.assert_not_awaited()


def test_recheck_unknown_check_rejected():
    from backend.app import app
    from fastapi.testclient import TestClient
    response=TestClient(app).post('/api/recheck',headers={'X-Monitor-Action':'manual'},json={'app_id':'billing-local','check':'arbitrary'})
    assert response.status_code==404
