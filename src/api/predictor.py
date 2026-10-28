"""Prediction logic for the API (no web framework here, so it can be tested on its own).

Features are built exactly as in src/models/train_baseline.py:
  pct_now, log_list, share_<band> x6, d_pct, d_list_pct, post_break, specialty_code
A consistency test (tests/test_predictor.py) checks the two stay in step.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

STANDARD = 0.92
MIN_LIST = 100
BREAK_MONTH = pd.Timestamp("2026-03-01")
BANDS = ["wk_0_6", "wk_6_12", "wk_12_18", "wk_18_26", "wk_26_52", "wk_52_plus"]
DEFAULT_FEATURES = (["pct_now", "log_list", "d_pct", "d_list_pct", "post_break"]
                    + [f"share_{b}" for b in BANDS] + ["specialty_code"])
LABELS = {
    "pct_now": "Current % within 18 weeks",
    "log_list": "Size of the waiting list",
    "d_pct": "Change in % within 18 weeks last month",
    "d_list_pct": "Change in list size last month",
    "share_wk_0_6": "Share waiting 0-6 weeks",
    "share_wk_6_12": "Share waiting 6-12 weeks",
    "share_wk_12_18": "Share waiting 12-18 weeks",
    "share_wk_18_26": "Share waiting 18-26 weeks",
    "share_wk_26_52": "Share waiting 26-52 weeks",
    "share_wk_52_plus": "Share waiting over 52 weeks",
}
NOTICE = ("Aggregate forecast for a service, not for any individual patient. It is only a few per cent "
          "better than 'same as last month' (see the model card). Informational only, not clinical advice.")


class ServiceNotFound(LookupError):
    """Unknown trust, specialty or month."""


class NotEnoughData(ValueError):
    """The service exists but cannot be forecast (too small, or no previous month)."""


def _num(x):
    """JSON-safe number."""
    x = float(x)
    return None if np.isnan(x) or np.isinf(x) else round(x, 4)


class Predictor:
    def __init__(self, df: pd.DataFrame, model, meta: dict | None = None):
        self.df, self.model, self.meta = df, model, meta or {}
        feats = self.meta.get("features", DEFAULT_FEATURES)
        self.numeric = [f for f in feats if f != "specialty_code"]
        self.columns = self.numeric + ["specialty_code"]
        self.months = [pd.Timestamp(m) for m in sorted(df["month"].unique())]
        self.latest = self.months[-1]
        self._ref_cache: dict = {}

    @classmethod
    def from_files(cls, master="data/processed/rtt_master.csv", model="models/baseline_v1.joblib",
                   meta="models/baseline_v1_metadata.json") -> "Predictor":
        df = pd.read_csv(master, parse_dates=["month"])
        m = json.loads(Path(meta).read_text()) if Path(meta).exists() else {}
        return cls(df, joblib.load(model), m)

    # ------------------------------------------------------------------ features
    def _features(self, cur: pd.DataFrame, prev: pd.DataFrame, month: pd.Timestamp) -> pd.DataFrame:
        f = cur.merge(prev[["trust_code", "specialty_code", "pct_within_18w", "waiting_list"]]
                      .rename(columns={"pct_within_18w": "prev_pct", "waiting_list": "prev_list"}),
                      on=["trust_code", "specialty_code"], how="left")
        f["pct_now"] = f["pct_within_18w"]
        f["log_list"] = np.log(f["waiting_list"].where(f["waiting_list"] > 0))
        for b in BANDS:
            f[f"share_{b}"] = f[b] / f["waiting_list"].where(f["waiting_list"] > 0)
        f["d_pct"] = f["pct_now"] - f["prev_pct"]
        f["d_list_pct"] = (f["waiting_list"] - f["prev_list"]) / f["prev_list"].where(f["prev_list"] > 0)
        f["post_break"] = int((month + pd.offsets.MonthBegin(1)) >= BREAK_MONTH)
        return f

    def _month(self, month) -> pd.Timestamp:
        if month is None:
            return self.latest
        month = pd.Timestamp(month)
        if month not in self.months:
            raise ServiceNotFound(f"No data for {month:%Y-%m}. Available: {self.months[0]:%Y-%m} to {self.latest:%Y-%m}.")
        return month

    def _reference(self, month: pd.Timestamp) -> pd.Series:
        """Typical (median) feature values across all services in the month."""
        if month not in self._ref_cache:
            cur = self.df[(self.df["month"] == month) & (self.df["waiting_list"] >= MIN_LIST)]
            prev = self.df[self.df["month"] == month - pd.offsets.MonthBegin(1)]
            f = self._features(cur, prev, month)
            self._ref_cache[month] = f[self.numeric].median()
        return self._ref_cache[month]

    # ------------------------------------------------------------------ prediction
    def predict(self, trust_code: str, specialty_code: str, month=None) -> dict:
        month = self._month(month)
        prev_month = month - pd.offsets.MonthBegin(1)
        rows = self.df[(self.df["trust_code"] == trust_code) & (self.df["specialty_code"] == specialty_code)]
        if rows.empty:
            raise ServiceNotFound(f"No service found for trust '{trust_code}' and specialty '{specialty_code}'. "
                                  "Trust codes that merged (e.g. RVJ) appear under their new code (RA7).")
        cur = rows[rows["month"] == month]
        if cur.empty:
            raise NotEnoughData(f"This service has no data for {month:%Y-%m} (the trust may not have reported).")
        if float(cur["waiting_list"].iloc[0]) < MIN_LIST:
            raise NotEnoughData(f"Fewer than {MIN_LIST} pathways, so the percentage is too noisy to forecast.")
        f = self._features(cur, rows[rows["month"] == prev_month], month)
        x = f[self.columns].copy()
        if x[self.numeric].isna().any(axis=None):
            raise NotEnoughData(f"Needs data for {prev_month:%Y-%m} as well, which this service does not have.")

        delta = float(self.model.predict(x)[0])
        r = f.iloc[0]
        pct_now = float(r["pct_now"])
        forecast = float(np.clip(pct_now + delta, 0, 1))

        # Approximate drivers: swap each input for the typical value and see how the forecast moves.
        ref = self._reference(month)
        drivers = []
        for name in self.numeric:
            if name == "post_break" or pd.isna(ref[name]):
                continue
            x2 = x.copy()
            x2[name] = ref[name]
            effect = (delta - float(self.model.predict(x2)[0])) * 100
            drivers.append({"feature": name, "label": LABELS.get(name, name), "value": _num(r[name]),
                            "typical_value": _num(ref[name]), "effect_pp": round(effect, 3)})
        drivers = sorted(drivers, key=lambda d: abs(d["effect_pp"]), reverse=True)[:3]

        over = float(r["waiting_list"] - r["within_18w"])
        treat = max(0.0, (over - (1 - STANDARD) * r["waiting_list"]) / STANDARD)
        met = self.meta.get("metrics", {})
        nai = self.meta.get("naive_metrics", {})
        return {
            "trust_code": trust_code, "trust_name": str(r["trust_name"]),
            "specialty_code": specialty_code, "specialty": str(r["specialty"]),
            "icb_name": str(r["icb_name"]) if "icb_name" in f else None,
            "month": f"{month:%Y-%m}", "forecast_month": f"{month + pd.offsets.MonthBegin(1):%Y-%m}",
            "waiting_list": int(r["waiting_list"]),
            "current_pct_within_18w": round(pct_now * 100, 2),
            "forecast_pct_within_18w": round(forecast * 100, 2),
            "forecast_change_pp": round((forecast - pct_now) * 100, 2),
            "patients_waiting_12_18w": int(r["wk_12_18"]),
            "patients_to_treat_for_92": int(np.ceil(treat)),
            "drivers": drivers,
            "model": {"name": self.meta.get("model", "gradient_boosting"),
                      "test_mae_pp": met.get("MAE_pp"), "same_as_last_month_mae_pp": nai.get("MAE_pp"),
                      "test_months": self.meta.get("test_months")},
            "notice": NOTICE,
        }

    def search_services(self, text: str = "", month=None, limit: int = 20) -> list[dict]:
        """Find trust/specialty combinations (for drop-downs)."""
        month = self._month(month)
        cur = self.df[(self.df["month"] == month) & (self.df["waiting_list"] >= MIN_LIST)]
        if text:
            t = text.lower()
            cur = cur[cur["trust_name"].str.lower().str.contains(t, regex=False)
                      | cur["specialty"].str.lower().str.contains(t, regex=False)
                      | (cur["trust_code"].str.lower() == t)]
        cur = cur.sort_values("waiting_list", ascending=False).head(limit)
        return [{"trust_code": r.trust_code, "trust_name": r.trust_name, "specialty_code": r.specialty_code,
                 "specialty": r.specialty, "waiting_list": int(r.waiting_list)} for r in cur.itertuples()]