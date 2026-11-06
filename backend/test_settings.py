import copy
import importlib
import json
import asyncio
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient

monitor = importlib.import_module('backend.app')

def setup_settings(monkeypatch, tmp_path):
    candidate = copy.deepcopy(monitor.settings)
    monkeypatch.setattr(monitor, 'settings', copy.deepcopy(candidate))
    monkeypatch.setattr(monitor, 'config', copy.deepcopy(monitor.config))
    monkeypatch.setattr(monitor, 'SETTINGS_PATH', tmp_path / 'config.xml')
    return candidate

def test_settings_persist_and_validate(monkeypatch, tmp_path):
    data = setup_settings(monkeypatch, tmp_path)
    client = TestClient(monitor.app)
    headers = {'X-Monitor-Action':'manual'}
    data['dashboard']['refreshSeconds'] = 60
    data['apps'][0]['enabled'] = False
    assert client.put('/api/settings', json=data).status_code == 403
    assert client.put('/api/settings', json=data, headers={**headers,'Origin':'https://example.com'}).status_code == 403
    assert client.put('/api/settings', json=data, headers=headers).status_code == 200
    assert monitor.read_settings_xml(monitor.SETTINGS_PATH)[1] == data
    assert client.get('/api/settings').json() == monitor.public_settings(data)
    data['dashboard']['refreshSeconds'] = 1
    assert client.put('/api/settings', json=data, headers=headers).status_code == 422
    assert client.get('/api/settings').json()['dashboard']['refreshSeconds'] == 60
    data['dashboard']['refreshSeconds'] = 60
    data['apps'][0]['siteUrl'] = 'https://user:password@example.com'
    assert client.put('/api/settings', json=data, headers=headers).status_code == 422

def test_disabled_apps_make_no_requests(monkeypatch, tmp_path):
    data = setup_settings(monkeypatch, tmp_path)
    for app in data['apps']:
        app['enabled'] = False
    data['localMetrics'] = False
    client = TestClient(monitor.app)
    assert client.put('/api/settings', json=data, headers={'X-Monitor-Action':'manual'}).status_code == 200
    check = AsyncMock(side_effect=AssertionError('Disabled app checked'))
    monkeypatch.setattr(monitor, 'check_application', check)
    monkeypatch.setattr(monitor, 'internet_check', AsyncMock(return_value=monitor.result('ok','Online')))
    assert client.get('/api/live').json()['apps'] == []
    check.assert_not_awaited()
    assert client.post('/api/recheck',json={'app_id':data['apps'][0]['id'],'check':'Website'},headers={'X-Monitor-Action':'manual'}).status_code == 404

def test_disabled_check_skips_probe(monkeypatch):
    website = AsyncMock(side_effect=AssertionError('Disabled website checked'))
    monkeypatch.setattr(monitor,'website_check',website)
    item={'id':'test','name':'Test','backend':'http','siteUrl':'http://example.com','disabledChecks':['Website','Website SSL']}
    response=asyncio.run(monitor.check_application(None,item))
    assert response['checks'] == {}
    assert response['status'] == 'unknown'
    website.assert_not_awaited()

def test_failed_write_retains_previous_settings(monkeypatch, tmp_path):
    data = setup_settings(monkeypatch, tmp_path)
    previous=copy.deepcopy(monitor.settings)
    data['dashboard']['tableView'] = not data['dashboard']['tableView']
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(monitor.os,'replace',fail)
    client=TestClient(monitor.app)
    assert client.put('/api/settings',json=data,headers={'X-Monitor-Action':'manual'}).status_code == 500
    assert monitor.settings == previous


def test_brand_environment_roundtrip(monkeypatch, tmp_path):
    data = setup_settings(monkeypatch, tmp_path)
    data['apps'][0].update(brand='Greentrends', environment='uat')
    client = TestClient(monitor.app)
    headers={'X-Monitor-Action':'manual'}
    assert client.put('/api/settings',json=data,headers=headers).status_code == 200
    saved=monitor.read_settings_xml(monitor.SETTINGS_PATH)[1]
    assert saved['apps'][0]['brand'] == 'Greentrends'
    assert saved['apps'][0]['environment'] == 'uat'
    data['apps'][0]['environment']='invalid'
    assert client.put('/api/settings',json=data,headers=headers).status_code == 422
    assert monitor.settings['apps'][0]['environment'] == 'uat'
