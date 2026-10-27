"""Which trust codes are missing in some months, and how much do they matter?

Usage (from the project root):
    python src/pipeline/check_coverage.py

Writes data/processed/rtt_balanced.csv: only trust/specialty pairs that
appear in ALL months (use this for time-series modelling).
"""
import pandas as pd

MASTER = "data/processed/rtt_master.csv"
BALANCED = "data/processed/rtt_balanced.csv"


def main() -> None:
    df = pd.read_csv(MASTER, parse_dates=["month"])
    df["ym"] = df["month"].dt.strftime("%Y-%m")
    all_m = sorted(df["ym"].unique())
    n_months = len(all_m)

    # One row per trust CODE (names change after mergers/renames, codes are the key)
    latest_name = (df.sort_values("month").groupby("trust_code")["trust_name"].last())
    t = df.groupby("trust_code").agg(
        months=("ym", "nunique"),
        first=("ym", "min"),
        last=("ym", "max"),
        avg_waiting_list=("waiting_list", lambda s: s.sum() / n_months),
    )
    t["name"] = latest_name
    names_per_code = df.groupby("trust_code")["trust_name"].nunique()
    print(f"{len(t)} trust codes; {(names_per_code > 1).sum()} codes changed name during the period")

    partial = t[t["months"] < n_months].sort_values("avg_waiting_list", ascending=False)
    print(f"{len(partial)} codes not present in all {n_months} months\n")

    present = df.groupby("trust_code")["ym"].apply(set)
    print("Largest partial-coverage codes (first/last month seen, months missing inside that range):")
    for code, r in partial.head(15).iterrows():
        inside = [m for m in all_m if r["first"] <= m <= r["last"] and m not in present[code]]
        print(f"  {code}  {r['name'][:45]:45s} first={r['first']} last={r['last']} gaps={inside}")

    new_codes = t[t["first"] > all_m[0]].sort_values("avg_waiting_list", ascending=False)
    print("\nLargest codes that APPEAR part-way through (possible new merged-trust codes):")
    print(new_codes[["name", "first", "avg_waiting_list"]].head(10).to_string())

    counts = df.groupby(["trust_code", "specialty_code"])["ym"].transform("nunique")
    bal = df[counts == n_months].drop(columns="ym")
    bal.to_csv(BALANCED, index=False)
    print(f"\nBalanced panel: {len(bal):,} of {len(df):,} rows kept "
          f"({bal['waiting_list'].sum() / df['waiting_list'].sum():.1%} of all waiting-list volume)")


if __name__ == "__main__":
    main()