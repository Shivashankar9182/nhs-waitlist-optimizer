# %% [markdown]
# # 01 - Exploratory Data Analysis: NHS RTT waiting lists (Sep 2025 - Aug 2026)
# Run cell by cell in VS Code (Interactive Window), or as a script:
#   py notebooks/01_eda.py
# Figures are saved to reports/figures/.
# Needs: pip install matplotlib

# %%
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})
FIG = Path("reports/figures")
FIG.mkdir(parents=True, exist_ok=True)
STANDARD = 0.92

full = pd.read_csv("data/processed/rtt_master.csv", parse_dates=["month"])
bal = pd.read_csv("data/processed/rtt_balanced.csv", parse_dates=["month"])
latest = full["month"].max()
print(f"{full['month'].nunique()} months, {full['trust_code'].nunique()} trusts, latest = {latest:%b %Y}")


def national(df):
    g = df.groupby("month")[["waiting_list", "within_18w"]].sum()
    g["pct_within_18w"] = g["within_18w"] / g["waiting_list"]
    return g


nat_full, nat_bal = national(full), national(bal)

# %% [markdown]
# ## 1. National trend: all reporting trusts vs the same trusts every month
# The balanced line removes the effect of trusts entering/leaving the data.

# %%
fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ax[0].plot(nat_full.index, nat_full["waiting_list"] / 1e6, marker="o", label="All reporting trusts")
ax[0].plot(nat_bal.index, nat_bal["waiting_list"] / 1e6, marker="o", label="Same trusts every month")
ax[0].set(title="Waiting list size (millions of pathways)", ylabel="millions")
ax[0].legend()
ax[1].plot(nat_full.index, nat_full["pct_within_18w"] * 100, marker="o", label="All reporting trusts")
ax[1].plot(nat_bal.index, nat_bal["pct_within_18w"] * 100, marker="o", label="Same trusts every month")
ax[1].axhline(STANDARD * 100, color="red", ls="--", lw=1)
ax[1].text(nat_full.index[0], STANDARD * 100 - 4, "92% standard", color="red")
ax[1].set(title="% waiting up to 18 weeks", ylabel="%", ylim=(55, 95))
ax[1].legend()
for a in ax:
    a.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(FIG / "01_national_trend.png")
plt.show()

# %% [markdown]
# ## 2. The March 2026 step change: which specialties drove it?

# %%
spec = full.groupby(["month", "specialty"])[["waiting_list", "within_18w"]].sum()
spec["pct"] = spec["within_18w"] / spec["waiting_list"]
pct = spec["pct"].unstack("specialty")
feb, mar = pd.Timestamp("2026-02-01"), pd.Timestamp("2026-03-01")
if feb in pct.index and mar in pct.index:
    jump = ((pct.loc[mar] - pct.loc[feb]) * 100).sort_values()
    fig, ax = plt.subplots(figsize=(8, 6))
    jump.plot.barh(ax=ax, color="#2a6f97")
    ax.set(title="Change in % within 18 weeks, Feb to Mar 2026 (percentage points)", ylabel="")
    fig.tight_layout()
    fig.savefig(FIG / "02_march_jump_by_specialty.png")
    plt.show()
    print(jump.round(1).tail(5), "\n...\n", jump.round(1).head(3))

# %% [markdown]
# ## 3. Specialties in the latest month: size vs performance

# %%
s = full[full["month"] == latest].groupby("specialty")[["waiting_list", "within_18w"]].sum()
s["pct"] = s["within_18w"] / s["waiting_list"]
s = s.sort_values("waiting_list")
fig, ax = plt.subplots(1, 2, figsize=(13, 6), sharey=True)
ax[0].barh(s.index, s["waiting_list"] / 1e3, color="#2a6f97")
ax[0].set(title=f"Waiting list, {latest:%b %Y} (thousands)")
ax[1].barh(s.index, s["pct"] * 100, color="#e07a5f")
ax[1].axvline(92, color="red", ls="--", lw=1)
ax[1].set(title="% within 18 weeks", xlim=(40, 95))
fig.tight_layout()
fig.savefig(FIG / "03_specialties_latest.png")
plt.show()

# %% [markdown]
# ## 4. Trust variation (trusts with at least 5,000 pathways)

# %%
t = full[full["month"] == latest].groupby(["trust_code", "trust_name"])[["waiting_list", "within_18w"]].sum().reset_index()
t["pct"] = t["within_18w"] / t["waiting_list"]
big = t[t["waiting_list"] >= 5000]
print(f"{len(big)} trusts with >= 5,000 pathways; {(big['pct'] >= STANDARD).sum()} meet the 92% standard")

fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ax[0].hist(big["pct"] * 100, bins=20, color="#2a6f97")
ax[0].axvline(92, color="red", ls="--", lw=1)
ax[0].set(title="Trusts by % within 18 weeks", xlabel="%", ylabel="number of trusts")
ax[1].scatter(big["waiting_list"], big["pct"] * 100, s=14, alpha=0.7)
ax[1].set(xscale="log", title="Backlog size vs performance", xlabel="waiting list (log scale)", ylabel="% within 18 weeks")
fig.tight_layout()
fig.savefig(FIG / "04_trust_variation.png")
plt.show()

cols = ["trust_name", "waiting_list", "pct"]
print("Lowest 10:\n", big.nsmallest(10, "pct")[cols].round(3).to_string(index=False))
print("Highest 10:\n", big.nlargest(10, "pct")[cols].round(3).to_string(index=False))
print("Correlation (log backlog vs % within 18w):",
      round(pd.Series(big["waiting_list"]).apply(lambda x: __import__("math").log(x)).corr(big["pct"]), 3))

# %% [markdown]
# ## 5. Trust-level change in 18-week performance, Sep 2025 to Aug 2026 (balanced trusts)

# %%
b = bal.groupby(["trust_code", "month"])[["waiting_list", "within_18w"]].sum().reset_index()
b["pct"] = b["within_18w"] / b["waiting_list"]
first_m, last_m = b["month"].min(), b["month"].max()
w = b.pivot(index="trust_code", columns="month", values="pct")
size = b[b["month"] == last_m].set_index("trust_code")["waiting_list"]
chg = ((w[last_m] - w[first_m]) * 100)[size[size >= 5000].index].dropna()
print(f"Median change {first_m:%b %Y} -> {last_m:%b %Y}: {chg.median():+.1f} pp; "
      f"{(chg > 0).mean():.0%} of trusts improved")
fig, ax = plt.subplots(figsize=(7, 4))
ax.hist(chg, bins=25, color="#2a6f97")
ax.axvline(0, color="black", lw=1)
ax.set(title="Change in % within 18 weeks by trust (pp)", xlabel="percentage points", ylabel="trusts")
fig.tight_layout()
fig.savefig(FIG / "05_trust_change.png")
plt.show()

# %% [markdown]
# ## 6. Summary table for the report

# %%
summary = nat_full.copy()
summary["pct_within_18w"] = (summary["pct_within_18w"] * 100).round(2)
summary["same_trusts_pct"] = (nat_bal["pct_within_18w"] * 100).round(2)
summary.to_csv("reports/eda_national_summary.csv")
print(summary[["waiting_list", "pct_within_18w", "same_trusts_pct"]])