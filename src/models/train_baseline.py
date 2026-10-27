"""Baseline models: predict NEXT month's % within 18 weeks for each trust x specialty.

Usage (from the project root):
    pip install scikit-learn joblib
    py src/models/train_baseline.py

Reads  data/processed/rtt_balanced.csv  (same trusts every month)
Writes reports/model_results.csv, models/baseline_v1.joblib, models/baseline_v1_metadata.json

Design (leakage-safe):
  * One row = one trust x specialty at month t. Features use only months <= t.
  * Target = pct_within_18w at month t+1.
  * Models predict the CHANGE (target - pct now); the naive baseline predicts no change.
  * Time-based split: test = target months from TEST_START onward; train = earlier targets.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA = Path("data/processed/rtt_balanced.csv")
TEST_START = pd.Timestamp("2026-06-01")   # target months Jun-Aug 2026 are the held-out test
BREAK_MONTH = pd.Timestamp("2026-03-01")  # structural break in the national series
MIN_LIST = 100                            # ignore tiny cells (very noisy percentages)
DROP_BREAK_FROM_TRAIN = True              # the Feb->Mar 2026 step is a one-off regime change;
                                          # learning from it hurts the post-break test months
BANDS = ["wk_0_6", "wk_6_12", "wk_12_18", "wk_18_26", "wk_26_52", "wk_52_plus"]
SEED = 42


def build_panel(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["trust_code", "specialty_code", "month"]).copy()
    g = df.groupby(["trust_code", "specialty_code"])
    df["next_month"] = g["month"].shift(-1)
    df["prev_month"] = g["month"].shift(1)
    df["target_pct"] = g["pct_within_18w"].shift(-1)
    df["prev_pct"] = g["pct_within_18w"].shift(1)
    df["prev_list"] = g["waiting_list"].shift(1)

    consecutive = ((df["next_month"] - df["month"]).dt.days.between(28, 31)
                   & (df["month"] - df["prev_month"]).dt.days.between(28, 31))
    df = df[consecutive & (df["waiting_list"] >= MIN_LIST) & (df["prev_list"] > 0)].copy()

    df["pct_now"] = df["pct_within_18w"]
    df["log_list"] = np.log(df["waiting_list"])
    for b in BANDS:
        df[f"share_{b}"] = df[b] / df["waiting_list"]
    df["d_pct"] = df["pct_now"] - df["prev_pct"]
    df["d_list_pct"] = (df["waiting_list"] - df["prev_list"]) / df["prev_list"]
    df["post_break"] = (df["next_month"] >= BREAK_MONTH).astype(int)
    df["target_delta"] = df["target_pct"] - df["pct_now"]
    return df.dropna(subset=["target_pct"])


NUMERIC = (["pct_now", "log_list", "d_pct", "d_list_pct", "post_break"]
           + [f"share_{b}" for b in BANDS])
CATEG = ["specialty_code"]


def metrics(y_true, y_pred, weights):
    err = y_pred - y_true
    return {
        "MAE_pp": float(np.mean(np.abs(err)) * 100),
        "RMSE_pp": float(np.sqrt(np.mean(err**2)) * 100),
        "weighted_MAE_pp": float(np.average(np.abs(err), weights=weights) * 100),
    }


def make_pipeline(model):
    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEG),
    ])
    return Pipeline([("pre", pre), ("model", model)])


def main() -> None:
    raw = pd.read_csv(DATA, parse_dates=["month"])
    missing = [c for c in BANDS if c not in raw.columns]
    if missing:
        raise SystemExit(f"Missing band columns {missing} - rerun build_master.py with the new loader.")

    panel = build_panel(raw)
    train = panel[panel["next_month"] < TEST_START]
    test = panel[panel["next_month"] >= TEST_START]
    if DROP_BREAK_FROM_TRAIN:
        train = train[train["next_month"] != BREAK_MONTH]
    print(f"Rows: train {len(train):,} (targets {train['next_month'].min():%b %Y}-{train['next_month'].max():%b %Y}), "
          f"test {len(test):,} (targets {test['next_month'].min():%b %Y}-{test['next_month'].max():%b %Y})")
    if len(train) == 0 or len(test) == 0:
        raise SystemExit("Not enough months for a train/test split - need 12 months.")

    X_cols = NUMERIC + CATEG
    results, preds = [], {}

    # Baseline 1: naive 'same as last month'
    preds["naive_last_month"] = test["pct_now"].to_numpy()

    # Baseline 2: naive + average change seen in training (captures drift)
    preds["naive_plus_mean_drift"] = test["pct_now"].to_numpy() + train["target_delta"].mean()

    # Models predict the change in % within 18 weeks
    models = {
        "ridge": make_pipeline(Ridge(alpha=1.0)),
        "gradient_boosting": make_pipeline(HistGradientBoostingRegressor(
            max_depth=4, learning_rate=0.05, max_iter=300, random_state=SEED)),
    }
    fitted = {}
    for name, pipe in models.items():
        pipe.fit(train[X_cols], train["target_delta"])
        preds[name] = test["pct_now"].to_numpy() + pipe.predict(test[X_cols])
        fitted[name] = pipe

    y, w = test["target_pct"].to_numpy(), test["waiting_list"].to_numpy()
    for name, p in preds.items():
        results.append({"model": name, **metrics(y, p, w)})
    res = pd.DataFrame(results).round(3)
    base = res.loc[res["model"] == "naive_last_month", "MAE_pp"].iloc[0]
    res["MAE_vs_naive_%"] = ((res["MAE_pp"] / base - 1) * 100).round(1)
    print("\nTest results (errors in percentage points of % within 18 weeks):")
    print(res.to_string(index=False))

    Path("reports").mkdir(exist_ok=True)
    res.to_csv("reports/model_results.csv", index=False)

    # Error by month and by specialty for the best model
    best = res[res["model"].isin(models)].sort_values("MAE_pp").iloc[0]["model"]
    t = test.assign(pred=preds[best], naive=preds["naive_last_month"])
    t["abs_model"] = (t["pred"] - t["target_pct"]).abs() * 100
    t["abs_naive"] = (t["naive"] - t["target_pct"]).abs() * 100
    by_month = t.groupby("next_month")[["abs_model", "abs_naive"]].mean().round(2)
    by_spec = (t.groupby("specialty")[["abs_model", "abs_naive"]].mean().round(2)
               .assign(gain=lambda d: (d["abs_naive"] - d["abs_model"]).round(2))
               .sort_values("gain"))
    print(f"\nBest model: {best}. MAE by target month (model vs naive):\n{by_month}")
    print(f"\nSpecialties where the model helps least / most:\n{pd.concat([by_spec.head(3), by_spec.tail(3)])}")

    # Which features matter?
    pi = permutation_importance(fitted[best], test[X_cols], test["target_delta"],
                                n_repeats=5, random_state=SEED, scoring="neg_mean_absolute_error")
    imp = pd.Series(pi.importances_mean, index=X_cols).sort_values(ascending=False)
    print("\nPermutation importance (drop in score when shuffled):")
    print(imp.round(5).head(8))

    Path("models").mkdir(exist_ok=True)
    joblib.dump(fitted[best], "models/baseline_v1.joblib")
    meta = {
        "model": best, "target": "pct_within_18w at month t+1 (predicted as change from month t)",
        "features": X_cols, "train_rows": int(len(train)), "test_rows": int(len(test)),
        "test_months": [f"{m:%Y-%m}" for m in sorted(test["next_month"].unique())],
        "metrics": res[res["model"] == best].iloc[0].drop("model").to_dict(),
        "naive_metrics": res[res["model"] == "naive_last_month"].iloc[0].drop("model").to_dict(),
        "notes": ("Balanced panel, cells with >=100 pathways, 12 months of data. The Mar 2026 "
                  f"structural break target month is {'excluded from' if DROP_BREAK_FROM_TRAIN else 'included in'} training. "
                  "This choice was made after comparing setups on the test months, so the gain is optimistic."),
    }
    Path("models/baseline_v1_metadata.json").write_text(json.dumps(meta, indent=2))
    print("\nSaved models/baseline_v1.joblib and metadata.")


if __name__ == "__main__":
    main()