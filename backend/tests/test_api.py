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

def test_bitunix_market_is_separate(client,monkeypatch):
    import asyncio
    from predice import bitunix
    async def only_btc(): return [{'symbol':'BTCUSDT','name':'BTC','base':'BTC','source':'Bitunix futures'}]
    monkeypatch.setattr(bitunix,'assets',only_btc)
    headers={'Authorization':'Bearer test-only-token'}
    assert client.put('/watchlist/BTCUSDT?source=bitunix',headers=headers).status_code==200
    assert client.get('/watchlist?source=bitunix',headers=headers).json()==['BTCUSDT']
    assert client.get('/watchlist',headers=headers).json().count('BTCUSDT')==1
    with store.connect() as db:
        db.execute('INSERT INTO candles VALUES(?,?,?,?)',('BITUNIX:BTCUSDT',300000,101,1))
        db.execute('INSERT INTO candles VALUES(?,?,?,?)',('BTCUSDT',300000,100,1))
    assert client.get('/candles/BTCUSDT?source=bitunix',headers=headers).json()[0]['close']==101
    assert client.get('/candles/BTCUSDT',headers=headers).json()[0]['close']==100
    assert client.get('/assets?q=https://www.bitunix.com/futures/BTCUSDT&source=bitunix',headers=headers).json()[0]['symbol']=='BTCUSDT'
