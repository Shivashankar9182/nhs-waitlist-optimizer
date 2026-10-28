"""Run from the project root:  py -m pytest tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for sub in ("api", "models"):
    sys.path.insert(0, str(ROOT / "src" / sub))
import predictor as pr  # noqa: E402
import train_baseline as tb  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

BANDS = pr.BANDS


def make_df(n_trusts=12):
    rng = np.random.default_rng(3)
    rows = []
    for m in pd.period_range("2025-09", "2026-08", freq="M"):
        for t in range(n_trusts):
            for spec, name in [("C_100", "General Surgery Service"), ("C_300", "General Internal Medicine Service")]:
                b = rng.integers(200, 2500, 6)
                rows.append({"month": m.to_timestamp(), "trust_code": f"T{t:02d}", "trust_name": f"TRUST {t}",
                             "icb_name": "ICB X", "specialty_code": spec, "specialty": name,
                             **dict(zip(BANDS, b)), "waiting_list": b.sum(), "within_18w": b[:3].sum(),
                             "pct_within_18w": b[:3].sum() / b.sum()})
    return pd.DataFrame(rows)


def fitted():
    df = make_df()
    panel = tb.build_panel(df)
    cols = tb.NUMERIC + tb.CATEG
    pipe = tb.make_pipeline(HistGradientBoostingRegressor(max_iter=30, random_state=1))
    pipe.fit(panel[cols], panel["target_delta"])
    return df, panel, pipe


def test_matches_training_features():
    df, panel, pipe = fitted()
    p = pr.Predictor(df, pipe, {"features": tb.NUMERIC + tb.CATEG})
    row = panel[(panel["month"] == "2026-03-01")].iloc[0]
    out = p.predict(row["trust_code"], row["specialty_code"], "2026-03-01")
    expected = float(np.clip(row["pct_now"] + pipe.predict(panel.loc[[row.name], tb.NUMERIC + tb.CATEG])[0], 0, 1) * 100)
    assert abs(out["forecast_pct_within_18w"] - round(expected, 2)) < 0.011


def test_response_shape_and_drivers():
    df, _, pipe = fitted()
    out = pr.Predictor(df, pipe).predict("T01", "C_100")
    assert out["month"] == "2026-08" and out["forecast_month"] == "2026-09"
    assert len(out["drivers"]) == 3 and "notice" in out
    assert 0 <= out["forecast_pct_within_18w"] <= 100


def test_unknown_service_and_month():
    df, _, pipe = fitted()
    p = pr.Predictor(df, pipe)
    for args, exc in [(("NOPE", "C_100"), pr.ServiceNotFound), (("T01", "C_100", "2030-01"), pr.ServiceNotFound)]:
        try:
            p.predict(*args)
            assert False, "expected an error"
        except exc:
            pass


def test_first_month_has_no_previous_month():
    df, _, pipe = fitted()
    try:
        pr.Predictor(df, pipe).predict("T01", "C_100", "2025-09")
        assert False
    except pr.NotEnoughData:
        pass


def test_small_service_refused():
    df, _, pipe = fitted()
    df.loc[(df["trust_code"] == "T02") & (df["month"] == "2026-08"), "waiting_list"] = 50
    try:
        pr.Predictor(df, pipe).predict("T02", "C_100")
        assert False
    except pr.NotEnoughData:
        pass


def test_search():
    df, _, pipe = fitted()
    res = pr.Predictor(df, pipe).search_services("general surgery", limit=5)
    assert len(res) == 5 and all(r["specialty_code"] == "C_100" for r in res)