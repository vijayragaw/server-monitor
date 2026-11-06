import asyncio
import copy
import importlib
import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.servers import validate_server, validate_metrics, poll_server

monitor=importlib.import_module('backend.app')
TOKEN='a'*48

def server(**values):
    return {'id':'ubuntu-one','name':'Ubuntu production','kind':'remote','os':'ubuntu','agentUrl':'http://10.0.0.5:8449/v1/metrics','token':TOKEN,'enabled':True,**values}

def metrics(**values):
    return {'version':1,'collected_at':datetime.now(timezone.utc).isoformat(),'cpu_percent':80,'ram_percent':55,'disk_percent':93,'disk_free_bytes':7,'disk_total_bytes':100,'uptime_seconds':90000,**values}

def agent_module():
    spec=importlib.util.spec_from_file_location('ubuntu_metrics_agent',Path(__file__).resolve().parents[1]/'ubuntu-agent'/'agent.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_agent_authentication_and_live_metrics(monkeypatch,tmp_path):
    token_file=tmp_path/'token'
    token_file.write_text(TOKEN)
    monkeypatch.setenv('MONITOR_TOKEN_FILE',str(token_file))
    monkeypatch.setenv('MONITOR_DISK_PATH',str(tmp_path))
    client=TestClient(agent_module().create_app())
    assert client.get('/v1/metrics').status_code==401
    assert client.get('/v1/metrics',headers={'Authorization':'Bearer wrong'}).status_code==401
    response=client.get('/v1/metrics',headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==200
    assert response.headers['cache-control']=='no-store'
    validate_metrics(response.json())
    assert TOKEN not in response.text
    assert client.get('/openapi.json').status_code==404

def test_agent_rejects_short_token(monkeypatch,tmp_path):
    path=tmp_path/'token';path.write_text('short')
    monkeypatch.setenv('MONITOR_TOKEN_FILE',str(path))
    with pytest.raises(RuntimeError):agent_module().create_app()

@pytest.mark.parametrize('url',['http://example.com/v1/metrics','http://8.8.8.8/v1/metrics','https://user:password@example.com/v1/metrics','https://example.com/wrong','https://example.com/v1/metrics?token=secret'])
def test_unsafe_agent_urls_rejected(url):
    with pytest.raises(ValueError):validate_server(server(agentUrl=url))

@pytest.mark.parametrize('changes',[{'cpu_percent':101},{'ram_percent':float('nan')},{'uptime_seconds':-1},{'disk_free_bytes':101},{'collected_at':(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()}])
def test_bad_or_stale_metrics_rejected(changes):
    with pytest.raises(ValueError):validate_metrics(metrics(**changes))

def test_poll_statuses_auth_and_disabled():
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.headers['Authorization']=='Bearer '+TOKEN
        return httpx.Response(200,json=metrics())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await poll_server(server(),client)
            assert result['status']=='critical'
            assert result['checks']['CPU']['status']=='warning'
            assert result['checks']['RAM']['status']=='ok'
            assert TOKEN not in str(result)
            await poll_server(server(enabled=False),client)
            assert len(requests)==1
    asyncio.run(run())

def test_bad_auth_and_redirect_not_followed():
    async def run():
        for status in [401,302]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(status,headers={'Location':'https://elsewhere.example/v1/metrics'}))) as client:
                result=await poll_server(server(),client)
                assert result['status']=='unknown'
                assert not result['checks']
    asyncio.run(run())

def test_settings_tokens_are_redacted_and_preserved(monkeypatch,tmp_path):
    monkeypatch.setattr(monitor,'settings',copy.deepcopy(monitor.settings))
    monkeypatch.setattr(monitor,'config',copy.deepcopy(monitor.config))
    monkeypatch.setattr(monitor,'SETTINGS_PATH',tmp_path/'config.xml')
    data=copy.deepcopy(monitor.settings);data['servers']=[server()];data['apps'][0]['serverId']='ubuntu-one'
    client=TestClient(monitor.app);headers={'X-Monitor-Action':'manual'}
    response=client.put('/api/settings',json=data,headers=headers)
    assert response.status_code==200
    assert TOKEN not in response.text
    public=client.get('/api/settings').json()
    assert 'token' not in public['servers'][0] and public['servers'][0]['hasToken']
    public['servers'][0]['name']='Updated name'
    public['servers'][0]['token']=''
    assert client.put('/api/settings',json=public,headers=headers).status_code==200
    assert monitor.settings['servers'][0]['token']==TOKEN
    assert TOKEN in monitor.SETTINGS_PATH.read_text()
    public['servers']=[]
    assert client.put('/api/settings',json=public,headers=headers).status_code==422
    assert client.post('/api/servers/test',json=server()).status_code==403
    fake=AsyncMock(return_value={'status':'ok','summary':'Agent connected','checks':{}})
    monkeypatch.setattr(monitor,'poll_server',fake)
    assert client.post('/api/servers/test',json={**server(),'token':''},headers=headers).status_code==200
    assert fake.call_args.args[0]['token']==TOKEN
    assert client.put('/api/settings',json=[],headers=headers).status_code==422

def test_live_contains_server_readings_and_links(monkeypatch):
    monkeypatch.setattr(monitor,'config',{**monitor.config,'apps':[],'servers':[server()],'local_metrics':False})
    monkeypatch.setattr(monitor,'internet_check',AsyncMock(return_value={'status':'ok','summary':'Online'}))
    monkeypatch.setattr(monitor,'poll_server',AsyncMock(return_value={'id':'ubuntu-one','status':'ok','checks':{}}))
    response=TestClient(monitor.app).get('/api/live')
    assert response.status_code==200
    assert response.json()['servers'][0]['id']=='ubuntu-one'
    assert TOKEN not in response.text

def test_poller_reads_real_agent(monkeypatch,tmp_path):
    path=tmp_path/'token';path.write_text(TOKEN)
    monkeypatch.setenv('MONITOR_TOKEN_FILE',str(path))
    monkeypatch.setenv('MONITOR_DISK_PATH',str(tmp_path))
    app=agent_module().create_app()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1') as client:
            response=await poll_server(server(agentUrl='http://127.0.0.1/v1/metrics'),client)
            assert response['summary']=='Agent connected'
            assert set(response['checks'])=={'CPU','RAM','Disk','Free disk','Uptime'}
            assert TOKEN not in str(response)
    asyncio.run(run())
