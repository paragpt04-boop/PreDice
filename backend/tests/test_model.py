import numpy as np
import pytest
from predice.model import features, boundaries, forecast, HORIZONS
from predice.app import Calculation, calculate

def series(n=5000):
    rng=np.random.default_rng(71)
    return 100*np.exp(np.cumsum(rng.normal(0,.002,n))),rng.uniform(1,100,n)

def test_features_are_causal():
    c,v=series()
    np.testing.assert_array_equal(features(c,v)[:928],features(c[:1000],v[:1000]))

@pytest.mark.parametrize('h',HORIZONS.values())
def test_purging(h):
    tr,ca,te=boundaries(5000,h)
    assert tr.stop-1+h < ca.start
    assert ca.stop-1+h < te.start

def test_future_cannot_change_scaling_training_or_calibration():
    c,v=series()
    a=forecast(c,v,'1h')
    c2=c.copy(); c2[-100:]*=1.1
    b=forecast(c2,v,'1h')
    assert a['split']==b['split']
    assert 0<a['probability_up']<1
    assert a['lower_pct']<=a['expected_pct']<=a['upper_pct']
    assert a['data_hash']!=b['data_hash']
    assert a['fit_hash']==b['fit_hash']

def test_no_short_history():
    c,v=series(150)
    with pytest.raises(ValueError): forecast(c,v,'24h')

def test_costs_and_short():
    r=calculate(Calculation(side='SHORT',amount=1000,entry=100,exit=90,fee_bps=10,slippage_bps=0,stop=105))
    assert r['gross']==100
    assert r['costs']==pytest.approx(1.9)
    assert r['risk']==pytest.approx(52.05)

def test_settlement_uses_exact_target(tmp_path,monkeypatch):
    from predice import store
    monkeypatch.setattr(store,'DB',str(tmp_path/'test.db')); store.init()
    store.save_prediction('BTCUSDT',0,'5m',{'reference_price':100},1)
    with store.connect() as db: db.execute('INSERT INTO candles VALUES(?,?,?,?)',('BTCUSDT',600000,120,1))
    store.settle('BTCUSDT')
    with store.connect() as db: assert db.execute('SELECT outcome FROM predictions').fetchone()[0] is None
    with store.connect() as db: db.execute('INSERT INTO candles VALUES(?,?,?,?)',('BTCUSDT',300000,110,1))
    store.settle('BTCUSDT')
    with store.connect() as db: assert db.execute('SELECT outcome FROM predictions').fetchone()[0]==pytest.approx(10)
