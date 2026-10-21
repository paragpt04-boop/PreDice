import pytest
from fastapi.testclient import TestClient
from predice.app import app
from predice import store, market

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DB',str(tmp_path/'api.db'))
    monkeypatch.setenv('PREDICE_TOKEN','test-only-token')
    store.init()
    # Without context manager, lifespan does not start network workers.
    return TestClient(app)

def test_auth_required(client):
    assert client.get('/watchlist').status_code==401
    assert client.get('/watchlist',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/watchlist',headers={'Authorization':'Bearer test-only-token'}).status_code==200

def test_calculator_validation(client):
    headers={'Authorization':'Bearer test-only-token'}
    assert client.post('/calculate',headers=headers,json={'side':'LONG','amount':-1,'entry':100,'exit':110}).status_code==422
    assert client.post('/calculate',headers=headers,json={'side':'LONG','amount':100,'entry':100,'exit':110,'stop':105}).status_code==422

def test_stale_prediction_abstains(client):
    store.save_prediction('BTCUSDT',0,'5m',{'signal':'LONG','entry':100,'stop':99,'take_profit':102},1)
    item=client.get('/predictions/BTCUSDT',headers={'Authorization':'Bearer test-only-token'}).json()['items'][0]
    assert item['stale'] and item['signal']=='WAIT' and item['entry'] is None

def test_untrusted_link_not_fetched(monkeypatch):
    import asyncio
    async def forbidden(): raise AssertionError('Must not fetch anything')
    monkeypatch.setattr(market,'assets',forbidden)
    assert asyncio.run(market.search('http://169.254.169.254/latest/meta-data'))==[]

def test_short_horizon_expires_before_global_age_limit(client,monkeypatch):
    import importlib
    module=importlib.import_module('predice.app')
    monkeypatch.setattr(module.time,'time',lambda: 601)
    store.save_prediction('BTCUSDT',0,'5m',{'signal':'LONG','entry':100,'stop':99,'take_profit':102},1)
    item=client.get('/predictions/BTCUSDT',headers={'Authorization':'Bearer test-only-token'}).json()['items'][0]
    assert item['stale'] and item['signal']=='WAIT'
