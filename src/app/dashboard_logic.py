"""Pure-pandas logic for the dashboard (no Streamlit here, so it can be tested)."""
from pathlib import Path

import numpy as np
import pandas as pd

STANDARD = 0.92
BAND_COLS = ["wk_0_6", "wk_6_12", "wk_12_18", "wk_18_26", "wk_26_52", "wk_52_plus"]
BAND_LABELS = {"wk_0_6": "0-6 wks", "wk_6_12": "6-12 wks", "wk_12_18": "12-18 wks",
               "wk_18_26": "18-26 wks", "wk_26_52": "26-52 wks", "wk_52_plus": "52+ wks"}
BREAK_MONTH = pd.Timestamp("2026-03-01")


def load_master(path="data/processed/rtt_master.csv") -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["month"])
    missing = [c for c in BAND_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}. Rerun build_master.py with the latest loader.")
    return df


def add_metrics(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["over_18w"] = d["waiting_list"] - d["within_18w"]
    d["pct_within_18w"] = d["within_18w"] / d["waiting_list"].where(d["waiting_list"] > 0)
    d["at_risk_12_18"] = d["wk_12_18"]
    d["at_risk_share"] = d["wk_12_18"] / d["waiting_list"].where(d["waiting_list"] > 0)
    d["treat_to_reach_92"] = ((d["over_18w"] - (1 - STANDARD) * d["waiting_list"]) / STANDARD).clip(lower=0).apply(np.ceil)
    return d


def assign_tier(d: pd.DataFrame) -> pd.Series:
    """High: top 10% by patients at risk, or top 10% by share with above-median volume.
    Medium: top 25% on either. Low: the rest."""
    if d.empty:
        return pd.Series(dtype=object)
    v, sh = d["at_risk_12_18"], d["at_risk_share"]
    v90, v75, v50 = v.quantile(0.90), v.quantile(0.75), v.quantile(0.50)
    s90, s75 = sh.quantile(0.90), sh.quantile(0.75)
    out = pd.Series("Low", index=d.index)
    out[(v >= v75) | (sh >= s75)] = "Medium"
    out[(v >= v90) | ((sh >= s90) & (v >= v50))] = "High"
    return out


def national_series(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("month")[["waiting_list", "within_18w"] + BAND_COLS].sum()
    g = add_metrics(g)
    return g.reset_index()


def trust_series(df: pd.DataFrame, trust_code: str) -> pd.DataFrame:
    g = df[df["trust_code"] == trust_code].groupby("month")[["waiting_list", "within_18w"] + BAND_COLS].sum()
    return add_metrics(g).reset_index()


def service_table(df: pd.DataFrame, month, min_list=100, exclude_other=False) -> pd.DataFrame:
    """One row per trust x specialty for the month, with metrics and tier (tier computed on the full set)."""
    cur = df[(df["month"] == month) & (df["waiting_list"] >= min_list)]
    if exclude_other:
        cur = cur[~cur["specialty"].str.startswith("Other")]
    cells = add_metrics(cur)
    cells["risk_tier"] = assign_tier(cells)
    return cells


def attach_forecast(cells: pd.DataFrame, month, latest_month,
                    path="reports/breach_watchlist_cells.csv") -> pd.DataFrame:
    """Add the model forecast column if the watchlist file exists and the month is the latest."""
    p = Path(path)
    if month != latest_month or not p.exists():
        return cells
    f = pd.read_csv(p)
    if "forecast_change_pp" not in f.columns:
        return cells
    return cells.merge(f[["trust_code", "specialty_code", "forecast_change_pp"]],
                       on=["trust_code", "specialty_code"], how="left")


def what_if(row: dict, treated: float, breach_share: float) -> dict:
    """Scenario for one service.

    treated        patients treated or otherwise removed from the over-18-week group
    breach_share   share (0-1) of the 12-18 week band that crosses 18 weeks
    Ignores new referrals and all other patient flows - an illustrative stress test only.
    """
    treated = float(min(max(treated, 0), row["over_18w"]))
    breach = float(row["wk_12_18"]) * float(breach_share)
    new_list = row["waiting_list"] - treated
    new_within = row["within_18w"] - breach
    pct_new = new_within / new_list if new_list > 0 else np.nan
    return {"treated": treated, "breaching": breach, "new_list": new_list,
            "new_over_18w": row["over_18w"] + breach - treated, "new_pct": pct_new,
            "change_pp": (pct_new - row["pct_within_18w"]) * 100}