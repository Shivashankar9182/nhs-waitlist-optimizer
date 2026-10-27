"""Breach-risk watchlist: where are patients closest to breaching the 18-week standard?

Usage (from the project root; run next to train_baseline.py in src/models):
    py src/models/breach_watchlist.py [YYYY-MM]      (default: latest month)

Reads  data/processed/rtt_master.csv   (all reporting trusts)
       models/baseline_v1.joblib       (optional - adds the model's next-month forecast)
Writes reports/breach_watchlist_cells.csv   (trust x specialty, ranked)
       reports/breach_watchlist_trusts.csv  (trust level, ranked)

Aggregate NHS statistics only. This ranks services, not individual patients,
and is not a tool for clinical prioritisation.

Key columns
  at_risk_12_18      patients waiting >12 and <=18 weeks: they cross 18 weeks within ~6 weeks
                     unless treated or removed. NOT a forecast that they will all breach.
  at_risk_share      at_risk_12_18 / waiting_list
  treat_to_reach_92  patients who would have to leave the list (be treated) for this service to
                     reach 92% within 18 weeks:  (over_18w - 0.08*list) / 0.92
  risk_tier          High / Medium / Low (rules in tier(): uses both volume and share)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import train_baseline as tb

MASTER = Path("data/processed/rtt_master.csv")
MODEL = Path("models/baseline_v1.joblib")
STANDARD = 0.92
MIN_LIST = 100  # ignore very small services (noisy percentages)


def tier(df: pd.DataFrame) -> pd.Series:
    """Tiers use both volume (how many patients) and share (how concentrated).

    High:   patients at risk in the top 10% of services, OR share in the top 10% with above-median volume
    Medium: patients at risk in the top 25%, OR share in the top 25%
    Low:    everything else
    """
    v, sh = df["at_risk_12_18"], df["at_risk_share"]
    v90, v75, v50 = v.quantile(0.90), v.quantile(0.75), v.quantile(0.50)
    s90, s75 = sh.quantile(0.90), sh.quantile(0.75)
    out = pd.Series("Low", index=df.index)
    out[(v >= v75) | (sh >= s75)] = "Medium"
    out[(v >= v90) | ((sh >= s90) & (v >= v50))] = "High"
    return out


def add_metrics(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["over_18w"] = d["waiting_list"] - d["within_18w"]
    d["pct_within_18w"] = d["within_18w"] / d["waiting_list"]
    d["at_risk_12_18"] = d["wk_12_18"]
    d["at_risk_share"] = d["wk_12_18"] / d["waiting_list"]
    d["pct_if_12_18_all_breach"] = (d["within_18w"] - d["wk_12_18"]) / d["waiting_list"]
    d["treat_to_reach_92"] = ((d["over_18w"] - (1 - STANDARD) * d["waiting_list"]) / STANDARD).clip(lower=0).round()
    return d


def add_forecast(cells: pd.DataFrame, prev: pd.DataFrame, month) -> pd.DataFrame:
    """Attach the saved model's forecast of next month's % within 18 weeks."""
    if not MODEL.exists():
        return cells
    import joblib
    model = joblib.load(MODEL)
    f = cells.merge(prev[["trust_code", "specialty_code", "pct_within_18w", "waiting_list"]]
                    .rename(columns={"pct_within_18w": "prev_pct", "waiting_list": "prev_list"}),
                    on=["trust_code", "specialty_code"], how="left")
    f["pct_now"] = f["pct_within_18w"]
    f["log_list"] = np.log(f["waiting_list"])
    for b in tb.BANDS:
        f[f"share_{b}"] = f[b] / f["waiting_list"]
    f["d_pct"] = (f["pct_now"] - f["prev_pct"]).fillna(0)
    f["d_list_pct"] = ((f["waiting_list"] - f["prev_list"]) / f["prev_list"]).replace([np.inf, -np.inf], 0).fillna(0)
    f["post_break"] = int((month + pd.offsets.MonthBegin(1)) >= tb.BREAK_MONTH)
    pred = f["pct_now"] + model.predict(f[tb.NUMERIC + tb.CATEG])
    cells = cells.copy()
    cells["forecast_next_pct"] = pred.clip(0, 1).to_numpy()
    cells["forecast_change_pp"] = ((cells["forecast_next_pct"] - cells["pct_within_18w"]) * 100).round(2)
    return cells


def main() -> None:
    df = pd.read_csv(MASTER, parse_dates=["month"])
    months = sorted(df["month"].unique())
    month = pd.Timestamp(sys.argv[1] + "-01") if len(sys.argv) > 1 else months[-1]
    cur = df[(df["month"] == month) & (df["waiting_list"] >= MIN_LIST)]
    prev = df[df["month"] == month - pd.offsets.MonthBegin(1)]
    print(f"Watchlist for {month:%B %Y}: {len(cur):,} services, {cur['trust_code'].nunique()} trusts\n")

    cells = add_metrics(cur)
    cells["risk_tier"] = tier(cells)
    cells = add_forecast(cells, prev, month)
    cells = cells.sort_values("at_risk_12_18", ascending=False)
    cells["priority_rank"] = range(1, len(cells) + 1)

    keep = ["priority_rank", "risk_tier", "trust_name", "specialty", "waiting_list", "pct_within_18w",
            "at_risk_12_18", "at_risk_share", "pct_if_12_18_all_breach", "treat_to_reach_92"]
    if "forecast_next_pct" in cells:
        keep += ["forecast_next_pct", "forecast_change_pp"]
    keep += ["trust_code", "specialty_code", "icb_name"]
    Path("reports").mkdir(exist_ok=True)
    cells[keep].to_csv("reports/breach_watchlist_cells.csv", index=False)

    # Trust level
    sums = ["waiting_list", "within_18w", "wk_12_18"]
    t = cur.groupby(["trust_code", "trust_name", "icb_name"], as_index=False)[sums].sum()
    t = add_metrics(t)
    t["risk_tier"] = tier(t[t["waiting_list"] >= 1000]).reindex(t.index).fillna("Low")
    t = t.sort_values("at_risk_12_18", ascending=False)
    t["priority_rank"] = range(1, len(t) + 1)
    t[["priority_rank", "risk_tier", "trust_name", "icb_name", "waiting_list", "pct_within_18w", "at_risk_12_18",
       "at_risk_share", "treat_to_reach_92", "trust_code"]].to_csv("reports/breach_watchlist_trusts.csv", index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 38)
    fmt = {"pct_within_18w": "{:.1%}".format, "at_risk_share": "{:.1%}".format}
    print("Top 15 services by patients waiting 12-18 weeks:")
    print(cells.head(15)[["trust_name", "specialty", "waiting_list", "pct_within_18w", "at_risk_12_18",
                          "at_risk_share", "risk_tier"]].to_string(index=False, formatters=fmt))
    print("\nTop 10 trusts:")
    print(t.head(10)[["trust_name", "waiting_list", "pct_within_18w", "at_risk_12_18", "at_risk_share"]]
          .to_string(index=False, formatters=fmt))
    s = cur.groupby("specialty")[sums].sum().pipe(add_metrics).sort_values("at_risk_12_18", ascending=False)
    print("\nBy specialty (England):")
    print(s.head(8)[["waiting_list", "pct_within_18w", "at_risk_12_18", "at_risk_share"]]
          .to_string(formatters=fmt))
    print(f"\nEngland: {int(cur['wk_12_18'].sum()):,} patients are in the 12-18 week band "
          f"({cur['wk_12_18'].sum() / cur['waiting_list'].sum():.1%} of the list).")
    print(f"Tiers: {cells['risk_tier'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()