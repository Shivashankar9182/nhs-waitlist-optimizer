"""Run from the project root:  py -m pytest tests -q"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "genai"))
import weekly_summary as ws  # noqa: E402

BANDS = ["wk_0_6", "wk_6_12", "wk_12_18", "wk_18_26", "wk_26_52", "wk_52_plus"]


def make_df():
    rng = np.random.default_rng(0)
    rows = []
    for m in pd.period_range("2026-06", "2026-08", freq="M"):
        for t, (code, name) in enumerate([("AAA", "ALPHA NHS TRUST"), ("BBB", "BETA NHS TRUST"), ("CCC", "GAMMA NHS TRUST")]):
            if code == "CCC" and str(m) == "2026-08":
                continue                                   # CCC stops reporting in August
            for spec in ["Cardiology Service", "Dermatology Service", "Other - Medical Services"]:
                b = rng.integers(500, 3000, 6)
                rows.append({"month": m.to_timestamp(), "trust_code": code, "trust_name": name,
                             "specialty": spec, **dict(zip(BANDS, b)),
                             "waiting_list": b.sum(), "within_18w": b[:3].sum()})
    return pd.DataFrame(rows)


def test_facts_basic():
    df = make_df()
    f = ws.compute_facts(df)
    aug = df[df["month"] == "2026-08-01"]
    assert f["waiting_list"] == int(aug["waiting_list"].sum())
    assert f["trusts_reporting"] == 2
    assert f["not_reporting"][0]["trust"] == "Gamma NHS Trust"
    assert all("Other" not in s["service"] for s in f["top_at_risk_services"])


def test_like_for_like_ignores_trust_that_left():
    df = make_df()
    f = ws.compute_facts(df)
    both = df[df["trust_code"].isin(["AAA", "BBB"])]
    cur, pre = both[both["month"] == "2026-08-01"], both[both["month"] == "2026-07-01"]
    assert f["list_change_like_for_like"] == int(cur["waiting_list"].sum() - pre["waiting_list"].sum())


def test_verify_accepts_supported_and_rejects_invented_numbers():
    f = ws.compute_facts(make_df())
    ok = f"The list was {f['waiting_list']:,} and {f['pct_within_18w']}% waited up to 18 weeks."
    assert ws.verify_numbers(ok, f) == []
    assert ws.verify_numbers("The list was 7,777,777.", f) == ["7777777"]


def test_template_passes_its_own_verification():
    f = ws.compute_facts(make_df())
    assert ws.verify_numbers(ws.template_summary(f), f) == []


def test_generate_falls_back_when_llm_invents_numbers(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "LOG_PATH", tmp_path / "log.jsonl")
    out = ws.generate(make_df(), llm=lambda s, u: "There were 1,234,567 patients waiting.")
    assert out["source"] == "template" and out["issues"]
    assert ws.DISCLAIMER in out["text"]


def test_generate_uses_llm_when_numbers_are_supported(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "LOG_PATH", tmp_path / "log.jsonl")
    f = ws.compute_facts(make_df())
    out = ws.generate(make_df(), llm=lambda s, u: f"{f['waiting_list']:,} pathways were waiting in {f['month']}.")
    assert out["source"] == "llm"


def test_generate_survives_api_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(ws, "LOG_PATH", tmp_path / "log.jsonl")

    def boom(s, u):
        raise RuntimeError("network down")

    out = ws.generate(make_df(), llm=boom)
    assert out["source"] == "template" and "LLM call failed" in out["issues"][0]