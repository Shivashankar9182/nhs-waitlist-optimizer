"""Validate the master RTT dataset and print the national monthly KPIs.

Usage (from the project root):
    python src/pipeline/validate_master.py

Reads data/processed/rtt_master.csv, runs checks, and writes
data/processed/national_kpis.csv for the dashboard.
"""
from pathlib import Path

import pandas as pd

MASTER = Path("data/processed/rtt_master.csv")
STANDARD = 0.92  # NHS constitutional standard: 92% within 18 weeks


def main() -> None:
    df = pd.read_csv(MASTER, parse_dates=["month"])
    problems = []

    # 1. Schema
    needed = {"month", "trust_code", "specialty_code", "waiting_list",
              "within_18w", "over_18w", "pct_within_18w"}
    missing = needed - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    # 2. Months present
    months = sorted(df["month"].dt.strftime("%Y-%m").unique())
    print(f"Months ({len(months)}): {months[0]} -> {months[-1]}")
    if len(months) < 12:
        problems.append(f"Only {len(months)} months present (want 12)")
    expected = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
    gaps = sorted(set(expected) - set(months))
    if gaps:
        problems.append(f"Gap months: {gaps}")

    # 3. Row integrity
    if df.duplicated(["month", "trust_code", "specialty_code"]).any():
        problems.append("Duplicate month/trust/specialty rows")
    if (df[["waiting_list", "within_18w", "over_18w"]] < 0).any().any():
        problems.append("Negative counts found")
    diff = (df["within_18w"] + df["over_18w"] - df["waiting_list"]).abs()
    if (diff > 1).any():
        problems.append(f"{(diff > 1).sum()} rows where within+over != total")

    # 4. Trusts reporting per month (a drop = missing submissions)
    per_month = df.groupby("month")["trust_code"].nunique()
    print("\nTrusts reporting per month:")
    print(per_month.to_string())
    # Judge coverage by waiting-list VOLUME, not by trust count (the count also
    # moves as small independent providers start/stop reporting).
    n_m = df["month"].nunique()
    in_all = df.groupby("trust_code")["month"].transform("nunique") == n_m
    partial_share = df.loc[~in_all, "waiting_list"].sum() / df["waiting_list"].sum()
    print(f"\nShare of volume from trusts not present in every month: {partial_share:.1%}")
    if partial_share > 0.05:
        problems.append(f"{partial_share:.1%} of volume comes from trusts missing in some months")

    # 5. National KPIs
    nat = df.groupby("month").agg(
        waiting_list=("waiting_list", "sum"),
        within_18w=("within_18w", "sum"),
        over_18w=("over_18w", "sum"),
        trusts=("trust_code", "nunique"),
    )
    nat["pct_within_18w"] = nat["within_18w"] / nat["waiting_list"]
    nat["gap_to_92pct"] = nat["pct_within_18w"] - STANDARD
    nat["waiting_list_change"] = nat["waiting_list"].diff()
    print("\nNational KPIs:")
    print(nat.round(4).to_string())
    nat.to_csv("data/processed/national_kpis.csv")

    print("\n" + ("PROBLEMS:\n- " + "\n- ".join(problems) if problems else "All checks passed."))


if __name__ == "__main__":
    main()