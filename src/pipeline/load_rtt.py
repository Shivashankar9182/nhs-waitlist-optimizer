"""Load and clean NHS England RTT full-extract CSV files.

Usage:
    python src/pipeline/load_rtt.py data/raw/20260831-RTT-August-2026-full-extract.csv

Output: one row per Provider x Specialty with waiting-list size and
18-week performance for the Incomplete Pathways part.
"""
import re
import sys
from pathlib import Path

import pandas as pd

WEEK_COLS_PREFIX = "Gt "
TOTAL_SPECIALTY = "C_999"  # NHS's own all-specialties total row (avoid double counting)

# Waiting-time bands, defined by the lower week of each 'Gt NN To MM Weeks' column.
# wk_12_18 = patients waiting more than 12 and up to 18 weeks, i.e. the group
# that is about to breach the 18-week standard.
BANDS = {
    "wk_0_6": (0, 6),
    "wk_6_12": (6, 12),
    "wk_12_18": (12, 18),
    "wk_18_26": (18, 26),
    "wk_26_52": (26, 52),
    "wk_52_plus": (52, 10**6),  # also includes the 'Gt 104 Weeks' column
}
BAND_COLS = list(BANDS)


def week_bands(df: pd.DataFrame) -> list[tuple[int, str]]:
    """Return (lower_week, column_name) for each 'Gt NN To MM Weeks' column."""
    bands = []
    for col in df.columns:
        m = re.match(r"Gt (\d+) To (\d+) Weeks SUM 1", col)
        if m:
            bands.append((int(m.group(1)), col))
    return sorted(bands)


def load_incomplete(path: str | Path) -> pd.DataFrame:
    """Load one monthly RTT extract and return cleaned incomplete-pathway data."""
    df = pd.read_csv(path)
    inc = df[df["RTT Part Description"] == "Incomplete Pathways"].copy()

    # Drop the NHS-supplied 'Total' specialty rows so sums are not doubled.
    inc = inc[inc["Treatment Function Code"] != TOTAL_SPECIALTY]

    # NONC = pathways commissioned by non-English commissioners. NHS England
    # excludes them from all published outputs (only the raw CSV has them),
    # so drop them to match the official figures.
    inc = inc[inc["Commissioner Org Code"] != "NONC"]

    bands = week_bands(inc)
    within_18 = [c for lo, c in bands if lo < 18]  # 0-1 ... 17-18 weeks
    over_18 = [c for lo, c in bands if lo >= 18] + ["Gt 104 Weeks SUM 1"]

    # Parse 'RTT-August-2026' -> 2026-08-01
    period = inc["Period"].str.replace("RTT-", "", regex=False)
    inc["month"] = pd.to_datetime("1 " + period, format="%d %B-%Y")

    for name, (lo_a, lo_b) in BANDS.items():
        cols = [c for lo, c in bands if lo_a <= lo < lo_b]
        if name == "wk_52_plus":
            cols = cols + ["Gt 104 Weeks SUM 1"]
        inc[name] = inc[cols].sum(axis=1)

    inc["within_18w"] = inc[within_18].sum(axis=1)
    inc["over_18w"] = inc[over_18].sum(axis=1)
    inc["waiting_list"] = inc["Total All"]

    keys = [
        "month",
        "Provider Org Code",
        "Provider Org Name",
        "Provider Parent Name",
        "Treatment Function Code",
        "Treatment Function Name",
    ]
    out = (
        inc.groupby(keys, as_index=False)[["waiting_list", "within_18w", "over_18w"] + BAND_COLS]
        .sum()
        .rename(
            columns={
                "Provider Org Code": "trust_code",
                "Provider Org Name": "trust_name",
                "Provider Parent Name": "icb_name",
                "Treatment Function Code": "specialty_code",
                "Treatment Function Name": "specialty",
            }
        )
    )
    # Sanity check: the first three bands must add up to within_18w.
    assert (out[["wk_0_6", "wk_6_12", "wk_12_18"]].sum(axis=1) == out["within_18w"]).all()
    out["pct_within_18w"] = (out["within_18w"] / out["waiting_list"]).where(
        out["waiting_list"] > 0
    )
    return out


if __name__ == "__main__":
    src = sys.argv[1]
    result = load_incomplete(src)
    print(result.head())
    print(f"{len(result):,} rows | {result['trust_code'].nunique()} trusts")
    print(f"Total waiting list: {result['waiting_list'].sum():,}")
    print(f"% within 18 weeks: {result['within_18w'].sum() / result['waiting_list'].sum():.1%}")