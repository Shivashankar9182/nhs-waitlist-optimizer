"""For trusts that stop reporting, see whether another trust in the same ICB
absorbed their waiting list (a merger) or the list simply vanished.

Usage (from the project root):
    python src/pipeline/trace_missing.py
"""
import pandas as pd

df = pd.read_csv("data/processed/rtt_master.csv", parse_dates=["month"])
df["ym"] = df["month"].dt.strftime("%Y-%m")
months = sorted(df["ym"].unique())

tot = df.groupby(["trust_code", "ym"])["waiting_list"].sum().unstack(fill_value=0)
info = df.groupby("trust_code").agg(name=("trust_name", "last"), icb=("icb_name", "last"),
                                    last=("ym", "max"))

stopped = info[info["last"] < months[-1]].copy()
stopped["size_last_month"] = [tot.loc[c, r["last"]] for c, r in stopped.iterrows()]
stopped = stopped[stopped["size_last_month"] >= 5000].sort_values("size_last_month", ascending=False)

for code, r in stopped.iterrows():
    nxt = months[months.index(r["last"]) + 1]
    same_icb = info[(info["icb"] == r["icb"]) & (info.index != code)].index
    change = (tot.loc[same_icb, nxt] - tot.loc[same_icb, r["last"]]).sort_values(ascending=False)
    print(f"\n{code} {r['name']} | last seen {r['last']} | list {int(r['size_last_month']):,}")
    print(f"  Biggest rises in same ICB in {nxt}:")
    for c, v in change.head(3).items():
        print(f"    {c} {info.loc[c, 'name'][:45]}  {int(v):+,}")