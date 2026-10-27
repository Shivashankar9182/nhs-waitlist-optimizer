"""Stack every monthly RTT CSV in data/raw into one master dataset.

Usage (from the project root):
    python src/pipeline/build_master.py

Reads:  data/raw/*.csv   (the extracted 'full extract' files, any month)
Writes: data/processed/rtt_master.csv
"""
from pathlib import Path

import pandas as pd

from load_rtt import BAND_COLS, load_incomplete

# Trust codes that merged into another code part-way through the period.
# RVJ (North Bristol) -> RA7 (Bristol NHS FT): RA7's list rose by ~44k in
# Jul 2026, the month RVJ stopped reporting (see trace_missing.py).
MERGE_MAP = {"RVJ": "RA7"}

RAW = Path("data/raw")
OUT = Path("data/processed/rtt_master.csv")


def main() -> None:
    files = sorted(RAW.glob("*.csv"))
    if not files:
        raise SystemExit("No CSV files found in data/raw - extract your ZIPs there first.")

    frames = []
    for f in files:
        print(f"Loading {f.name} ...")
        frames.append(load_incomplete(f))

    master = pd.concat(frames, ignore_index=True)
    # If a month was loaded twice, keep one copy.
    master = master.drop_duplicates(subset=["month", "trust_code", "specialty_code"])

    # Apply the merger map, then re-sum so each code/specialty/month is one row.
    master["trust_code"] = master["trust_code"].replace(MERGE_MAP)
    names = master.sort_values("month").groupby("trust_code")[["trust_name", "icb_name"]].last()
    master = master.groupby(["month", "trust_code", "specialty_code", "specialty"], as_index=False)[
        ["waiting_list", "within_18w", "over_18w"] + BAND_COLS
    ].sum()
    master = master.join(names, on="trust_code")
    master["pct_within_18w"] = (master["within_18w"] / master["waiting_list"]).where(
        master["waiting_list"] > 0
    )
    master = master.sort_values(["trust_code", "specialty_code", "month"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(OUT, index=False)

    months = sorted(master["month"].dt.strftime("%Y-%m").unique())
    print(f"\nSaved {len(master):,} rows to {OUT}")
    print(f"{len(months)} months: {months[0]} to {months[-1]}")
    print(f"{master['trust_code'].nunique()} trusts, {master['specialty_code'].nunique()} specialties")


if __name__ == "__main__":
    main()