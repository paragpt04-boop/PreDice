"""Chronological research model. No trading execution or guaranteed accuracy."""
import hashlib
import numpy as np
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

HORIZONS = {"5m": 1, "15m": 3, "1h": 12, "4h": 48, "24h": 288}
VERSION = "linear-boosted-platt-v2"

def features(close, volume):
    c, v = np.asarray(close, float), np.asarray(volume, float)
    if len(c) != len(v) or len(c) < 100 or not np.isfinite(c).all() or (c <= 0).any():
        raise ValueError("Invalid prices or insufficient history")
    rows = []
    for t in range(72, len(c)):
        r = np.diff(np.log(c[t-72:t+1]))
        rows.append([np.log(c[t]/c[t-k]) for k in (1,3,12,48,72)] +
                    [r[-12:].std(), r.std(), c[t]/c[t-23:t+1].mean()-1,
                     np.log1p(v[t])-np.log1p(v[t-23:t+1].mean())])
    x = np.asarray(rows)
    if not np.isfinite(x).all():
        raise ValueError("Non-finite features")
    return x

def boundaries(n, h):
    a, b = int(n*.55), int(n*.75)
    if a-h < 300 or b-a-h < 100 or n-b-h < 100:
        raise ValueError("Insufficient history for purged temporal validation")
    return slice(0,a-h), slice(a,b-h), slice(b,n)

def metrics(y, p, pred, lo, hi):
    labels = (y > 0).astype(int)
    bins = []
    ece = 0.
    for lower in np.arange(0,1,.1):
        mask = (p >= lower) & (p < lower+.1)
        if mask.any():
            rate, confidence = float(labels[mask].mean()), float(p[mask].mean())
            ece += float(mask.mean())*abs(rate-confidence)
            bins.append(dict(count=int(mask.sum()), probability=confidence, frequency=rate))
    return dict(samples=len(y), brier=float(np.mean((p-labels)**2)),
                ece=ece, mae_pct=float(np.mean(abs(y-pred))*100),
                coverage90=float(np.mean((y>=lo)&(y<=hi))), reliability=bins)

def forecast(close, volume, horizon):
    h = HORIZONS[horizon]
    c = np.asarray(close, float)
    x = features(c, volume)
    y = c[72+h:]/c[72:-h]-1
    xx = x[:-h]
    tr, ca, te = boundaries(len(y),h)
    scaler = StandardScaler().fit(xx[tr])
    z = scaler.transform(xx)
    labels = (y>0).astype(int)
    if len(np.unique(labels[tr]))<2 or len(np.unique(labels[ca]))<2:
        raise ValueError("Both directions required for calibration")
    reg = Ridge(alpha=20).fit(z[tr], y[tr])
    clf = LogisticRegression(C=.1, max_iter=1000).fit(z[tr], labels[tr])
    # Fixed, regularized nonlinear models. No random validation split or test tuning.
    options=dict(max_iter=80,max_leaf_nodes=7,learning_rate=.05,min_samples_leaf=80,
                 l2_regularization=10,early_stopping=False,random_state=71)
    nonlinear_reg=HistGradientBoostingRegressor(**options).fit(z[tr],y[tr])
    nonlinear_clf=HistGradientBoostingClassifier(**options).fit(z[tr],labels[tr])
    def expected(a):
        return .5*reg.predict(a)+.5*nonlinear_reg.predict(a)
    def raw_score(a):
        return .5*clf.decision_function(a)+.5*nonlinear_clf.decision_function(a)
    calibrator = LogisticRegression(C=1, max_iter=1000).fit(
        raw_score(z[ca]).reshape(-1,1), labels[ca])
    fit_hash=hashlib.sha256(b''.join(np.asarray(a).tobytes() for a in
        (scaler.mean_,scaler.scale_,reg.coef_,reg.intercept_,clf.coef_,clf.intercept_,
         calibrator.coef_,calibrator.intercept_,nonlinear_reg.predict(z[tr]),
         nonlinear_clf.decision_function(z[tr])))).hexdigest()
    def probability(a):
        return calibrator.predict_proba(raw_score(a).reshape(-1,1))[:,1]
    residual = abs(y[ca]-expected(z[ca]))
    # Finite-sample conformal quantile; empirical coverage only under market drift.
    q = float(np.quantile(residual, min(1,np.ceil((len(residual)+1)*.9)/len(residual)), method="higher"))
    predicted = expected(z[te]); p = probability(z[te])
    score = metrics(y[te],p,predicted,predicted-q,predicted+q)
    base = float(labels[tr].mean())
    score["baseline_brier"] = float(np.mean((base-labels[te])**2))
    score["zero_return_mae_pct"] = float(np.mean(abs(y[te]))*100)
    # Nonoverlapping observations make the effective sample count explicit.
    score["nonoverlap_samples"] = len(y[te][::h])
    score["nonoverlap_brier"] = float(np.mean((p[::h]-labels[te][::h])**2))
    latest = scaler.transform(x[-1:])
    expected_return, up = float(expected(latest)[0]), float(probability(latest)[0])
    qualified = (score["brier"] < score["baseline_brier"] and score["ece"] < .08
                 and score["coverage90"] >= .85 and score["nonoverlap_samples"] >= 100
                 and score["mae_pct"] < score["zero_return_mae_pct"])
    side = "WAIT"
    if qualified and expected_return-q > .002 and up >= .6: side="LONG"
    if qualified and expected_return+q < -.002 and up <= .4: side="SHORT"
    price = float(c[-1]); direction = 1 if side=="LONG" else -1
    risk = max(q, .003)
    return dict(horizon=horizon, model=VERSION, fit_hash=fit_hash,
        data_hash=hashlib.sha256(c.tobytes()+np.asarray(volume,float).tobytes()).hexdigest(),
        probability_up=up, expected_pct=expected_return*100, lower_pct=(expected_return-q)*100,
        upper_pct=(expected_return+q)*100, interval_nominal=.9, metrics=score,
        qualified=qualified, signal=side, reference_price=price,
        entry=price if side!="WAIT" else None,
        stop=price*(1-direction*risk) if side!="WAIT" else None,
        take_profit=price*(1+direction*risk*2) if side!="WAIT" else None,
        reason="Validated research signal; recheck spread and liquidity" if side!="WAIT" else
               "Abstention: evidence or net expected edge insufficient",
        split=dict(train_end=tr.stop+72-1, calibration_start=ca.start+72,
                   calibration_end=ca.stop+72-1, test_start=te.start+72, purge_bars=h))
