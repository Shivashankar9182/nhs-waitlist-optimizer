"""Try several modelling choices and see which (if any) clearly beats 'same as last month'.

Usage (from the project root, next to train_baseline.py in src/models):
    py src/models/run_ablations.py

For each setup it prints the naive error, the gradient-boosting error, the gain in
percentage points, and a 95% bootstrap interval for that gain. If the interval
includes 0, the improvement could be chance.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import train_baseline as tb

RNG = np.random.default_rng(0)
COUNT_COLS = ["waiting_list", "within_18w", "over_18w"] + tb.BANDS


def trust_level(raw: pd.DataFrame) -> pd.DataFrame:
    """Add specialties together so each trust is one series per month (less noisy)."""
    t = raw.groupby(["trust_code", "month"], as_index=False)[COUNT_COLS].sum()
    t["pct_within_18w"] = t["within_18w"] / t["waiting_list"].where(t["waiting_list"] > 0)
    t["specialty_code"] = "ALL"
    t["specialty"] = "All specialties"
    return t


def run(raw, label, min_list=100, drop_break=False, weight=False):
    tb.MIN_LIST = min_list
    panel = tb.build_panel(raw)
    train = panel[panel["next_month"] < tb.TEST_START]
    test = panel[panel["next_month"] >= tb.TEST_START]
    if drop_break:
        train = train[train["next_month"] != tb.BREAK_MONTH]
    cols = tb.NUMERIC + tb.CATEG
    pipe = tb.make_pipeline(HistGradientBoostingRegressor(
        max_depth=4, learning_rate=0.05, max_iter=300, random_state=tb.SEED))
    fit_kw = {"model__sample_weight": train["waiting_list"].to_numpy()} if weight else {}
    pipe.fit(train[cols], train["target_delta"], **fit_kw)

    y = test["target_pct"].to_numpy()
    pred = test["pct_now"].to_numpy() + pipe.predict(test[cols])
    err_model = np.abs(pred - y) * 100
    err_naive = np.abs(test["pct_now"].to_numpy() - y) * 100
    diff = err_naive - err_model                     # positive = model better
    boots = [diff[RNG.integers(0, len(diff), len(diff))].mean() for _ in range(500)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    w = test["waiting_list"].to_numpy()
    return {
        "setup": label, "train_rows": len(train), "test_rows": len(test),
        "naive_MAE": round(err_naive.mean(), 3), "model_MAE": round(err_model.mean(), 3),
        "gain_pp": round(diff.mean(), 3), "gain_95%_CI": f"[{lo:.3f}, {hi:.3f}]",
        "weighted_gain_pp": round(np.average(diff, weights=w), 3),
    }


def main() -> None:
    raw = pd.read_csv(tb.DATA, parse_dates=["month"])
    rows = [
        run(raw, "A. as trained (cells >=100, all months)"),
        run(raw, "B. drop the Mar-2026 break from training", drop_break=True),
        run(raw, "C. only cells >=500 pathways", min_list=500),
        run(raw, "D. weight training rows by list size", weight=True),
        run(raw, "E. B + C + D combined", min_list=500, drop_break=True, weight=True),
        run(trust_level(raw), "F. trust level (all specialties added)", min_list=500),
        run(trust_level(raw), "G. trust level, break dropped", min_list=500, drop_break=True),
    ]
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(out.to_string(index=False))
    out.to_csv("reports/ablation_results.csv", index=False)


if __name__ == "__main__":
    main()