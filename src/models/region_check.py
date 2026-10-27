"""Does the forecast work about equally well across areas (ICBs) and specialties?

Usage (from the project root, next to train_baseline.py in src/models):
    py src/models/region_check.py

Uses the saved model (models/baseline_v1.joblib) on the held-out test months and compares it
with 'same as last month' for every Integrated Care Board (ICB) and specialty.
Writes reports/region_check_icb.csv and reports/region_check_specialty.csv.
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import train_baseline as tb

MIN_ROWS = 60          # smallest group we report on (rows over the 3 test months)
WORSE_BY_PP = 0.25     # flag a group if the model is this much worse than 'same as last month'
HIGH_ERROR_X = 1.5     # flag a group if its model error is this many times the median group


def summarise(t: pd.DataFrame, by: str) -> pd.DataFrame:
    g = t.groupby(by).agg(rows=("pct_now", "size"),
                          naive_MAE=("err_naive", "mean"),
                          model_MAE=("err_model", "mean"),
                          avg_list=("waiting_list", "mean")).reset_index()
    g = g[g["rows"] >= MIN_ROWS].copy()
    g["gain_pp"] = g["naive_MAE"] - g["model_MAE"]
    med = g["model_MAE"].median()
    g["flag"] = np.where(g["gain_pp"] < -WORSE_BY_PP, "model worse than naive",
                np.where(g["model_MAE"] > HIGH_ERROR_X * med, "high error", ""))
    return g.sort_values("gain_pp").round(3)


def main() -> None:
    raw = pd.read_csv(tb.DATA, parse_dates=["month"])
    panel = tb.build_panel(raw)
    test = panel[panel["next_month"] >= tb.TEST_START].copy()
    model = joblib.load("models/baseline_v1.joblib")

    pred = test["pct_now"] + model.predict(test[tb.NUMERIC + tb.CATEG])
    test["err_model"] = (pred - test["target_pct"]).abs() * 100
    test["err_naive"] = (test["pct_now"] - test["target_pct"]).abs() * 100
    print(f"Test rows: {len(test):,} | overall MAE: naive {test['err_naive'].mean():.3f}, "
          f"model {test['err_model'].mean():.3f}\n")

    Path("reports").mkdir(exist_ok=True)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 45)
    for by, label, out in [("icb_name", "ICB", "reports/region_check_icb.csv"),
                           ("specialty", "specialty", "reports/region_check_specialty.csv")]:
        g = summarise(test, by)
        g.to_csv(out, index=False)
        n_better = int((g["gain_pp"] > 0).sum())
        print(f"=== By {label}: {len(g)} groups with >= {MIN_ROWS} rows ===")
        print(f"Model beats 'same as last month' in {n_better} of {len(g)} groups "
              f"({n_better / len(g):.0%}); model error ranges {g['model_MAE'].min():.2f} to "
              f"{g['model_MAE'].max():.2f} (median {g['model_MAE'].median():.2f}).")
        print("Largest losses vs naive:")
        print(g.head(5)[[by, "rows", "naive_MAE", "model_MAE", "gain_pp", "flag"]].to_string(index=False))
        print("Largest gains:")
        print(g.tail(5)[[by, "rows", "naive_MAE", "model_MAE", "gain_pp", "flag"]].to_string(index=False))
        print(f"Flagged groups: {int((g['flag'] != '').sum())}\n")


if __name__ == "__main__":
    main()