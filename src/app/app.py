"""NHS RTT waiting-list dashboard (Streamlit).

Run from the project root:
    pip install streamlit plotly pandas
    streamlit run src/app/app.py
Aggregate NHS England statistics only - not for clinical prioritisation of individuals.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard_logic import (BAND_COLS, BAND_LABELS, BREAK_MONTH, STANDARD, attach_forecast,
                             load_master, national_series, service_table, trust_series, what_if)

st.set_page_config(page_title="NHS Waiting List Optimizer", layout="wide")


@st.cache_data
def get_data():
    return load_master()


try:
    df = get_data()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load data/processed/rtt_master.csv: {e}")
    st.stop()

months = sorted(df["month"].unique())
latest = months[-1]

st.title("NHS Waiting List & Appointment Optimization")
st.caption("Illustrative student capstone built on NHS England RTT statistics (incomplete pathways). "
           "Not an official NHS system. Aggregate data: services are ranked, never individual patients.")

# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("Filters")
    month = st.selectbox("Month", months[::-1], index=0, format_func=lambda m: pd.Timestamp(m).strftime("%B %Y"))
    min_list = st.slider("Minimum waiting list", 0, 2000, 100, step=50)
    exclude_other = st.checkbox('Exclude catch-all "Other" specialties', value=True)
    tiers = st.multiselect("Risk tier", ["High", "Medium", "Low"], default=["High", "Medium"])
    specs_all = sorted(df["specialty"].unique())
    specs = st.multiselect("Specialty (blank = all)", specs_all)
    search = st.text_input("Trust name contains")
    sort_by = st.selectbox("Sort by", ["Patients waiting 12-18 weeks", "Share waiting 12-18 weeks",
                                       "Patients to treat to reach 92%", "Lowest % within 18 weeks"])

month = pd.Timestamp(month)
cells_all = service_table(df, month, min_list, exclude_other)
nat = national_series(df)
now = nat[nat["month"] == month].iloc[0]

tab1, tab2, tab3, tab4, tab5 = st.tabs(["National trend", "Watchlist", "Trust drill-down", "What-if", "About the data"])

# ---------------- Tab 1: national ----------------
with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Waiting list", f"{int(now['waiting_list']):,}")
    c2.metric("% within 18 weeks", f"{now['pct_within_18w']:.1%}", f"{(now['pct_within_18w'] - STANDARD) * 100:.1f} pp vs 92% standard")
    c3.metric("Waiting 12-18 weeks", f"{int(now['at_risk_12_18']):,}", f"{now['at_risk_share']:.1%} of list", delta_color="off")
    c4.metric("To treat to reach 92%", f"{int(now['treat_to_reach_92']):,}")

    left, right = st.columns(2)
    fig = go.Figure(go.Scatter(x=nat["month"], y=nat["waiting_list"] / 1e6, mode="lines+markers"))
    fig.update_layout(title="Waiting list (millions of pathways)", height=340, margin=dict(t=50, b=10))
    left.plotly_chart(fig, use_container_width=True)

    fig = go.Figure(go.Scatter(x=nat["month"], y=nat["pct_within_18w"] * 100, mode="lines+markers", name="% within 18 weeks"))
    fig.add_hline(y=STANDARD * 100, line_dash="dash", line_color="red")
    if nat["month"].min() <= BREAK_MONTH <= nat["month"].max():
        x0 = BREAK_MONTH.to_pydatetime()
        fig.add_shape(type="line", x0=x0, x1=x0, y0=0, y1=1, yref="paper", line=dict(dash="dot", color="grey"))
        fig.add_annotation(x=x0, y=1, yref="paper", text="Mar 2026 step change", showarrow=False, yanchor="bottom")
    fig.update_layout(title="% waiting up to 18 weeks (red = 92% standard)", height=340,
                      yaxis_range=[50, 95], margin=dict(t=50, b=10))
    right.plotly_chart(fig, use_container_width=True)
    st.info("National totals exclude trusts that did not submit data (e.g. Sheffield Teaching Hospitals for the whole "
            "period; Torbay and South Devon, Plymouth and Northampton General in later months). "
            "NHS England's headline figures include estimates for these, so they differ slightly.")

# ---------------- Tab 2: watchlist ----------------
with tab2:
    cells = attach_forecast(cells_all, month, latest)
    if tiers:
        cells = cells[cells["risk_tier"].isin(tiers)]
    if specs:
        cells = cells[cells["specialty"].isin(specs)]
    if search:
        cells = cells[cells["trust_name"].str.contains(search, case=False, na=False)]
    order = {"Patients waiting 12-18 weeks": ("at_risk_12_18", False),
             "Share waiting 12-18 weeks": ("at_risk_share", False),
             "Patients to treat to reach 92%": ("treat_to_reach_92", False),
             "Lowest % within 18 weeks": ("pct_within_18w", True)}[sort_by]
    cells = cells.sort_values(order[0], ascending=order[1])

    st.write(f"**{len(cells):,} services** match. Patients waiting 12-18 weeks cross the 18-week line within about six "
             "weeks unless treated; this is exposure, not a forecast that they will breach.")
    show = pd.DataFrame({
        "Tier": cells["risk_tier"], "Trust": cells["trust_name"], "Specialty": cells["specialty"],
        "Waiting list": cells["waiting_list"], "% within 18w": cells["pct_within_18w"] * 100,
        "Waiting 12-18w": cells["at_risk_12_18"], "Share 12-18w": cells["at_risk_share"] * 100,
        "To treat for 92%": cells["treat_to_reach_92"],
    })
    if "forecast_change_pp" in cells:
        show["Model forecast change (pp)"] = cells["forecast_change_pp"]
    st.dataframe(show.head(500), use_container_width=True, hide_index=True, height=520,
                 column_config={"% within 18w": st.column_config.NumberColumn(format="%.1f%%"),
                                "Share 12-18w": st.column_config.NumberColumn(format="%.1f%%"),
                                "Waiting list": st.column_config.NumberColumn(format="%d"),
                                "Waiting 12-18w": st.column_config.NumberColumn(format="%d"),
                                "To treat for 92%": st.column_config.NumberColumn(format="%d")})
    st.download_button("Download this view (CSV)", show.to_csv(index=False).encode("utf-8"),
                       file_name=f"watchlist_{month:%Y-%m}.csv", mime="text/csv")
    st.caption("Showing the first 500 rows; the download contains every row in the current filter.")

# ---------------- Tab 3: trust drill-down ----------------
with tab3:
    tr = (df[df["month"] == month].groupby(["trust_code", "trust_name"])["waiting_list"].sum()
          .reset_index().sort_values("waiting_list", ascending=False))
    tr["label"] = tr["trust_name"] + " (" + tr["trust_code"] + ")"
    pick = st.selectbox("Trust", tr["label"].tolist())
    code = tr.loc[tr["label"] == pick, "trust_code"].iloc[0]
    ts = trust_series(df, code)
    row = ts[ts["month"] == month]
    if row.empty:
        st.warning("This trust has no data for the selected month (it may not have submitted, or merged).")
    else:
        r = row.iloc[0]
        a, b, c, d = st.columns(4)
        a.metric("Waiting list", f"{int(r['waiting_list']):,}")
        b.metric("% within 18 weeks", f"{r['pct_within_18w']:.1%}")
        c.metric("Waiting 12-18 weeks", f"{int(r['at_risk_12_18']):,}")
        d.metric("To treat for 92%", f"{int(r['treat_to_reach_92']):,}")

        l, rt = st.columns(2)
        fig = go.Figure(go.Scatter(x=ts["month"], y=ts["pct_within_18w"] * 100, mode="lines+markers"))
        fig.add_hline(y=STANDARD * 100, line_dash="dash", line_color="red")
        fig.update_layout(title="% within 18 weeks", height=320, margin=dict(t=50, b=10))
        l.plotly_chart(fig, use_container_width=True)

        bands = pd.DataFrame({"Band": [BAND_LABELS[b] for b in BAND_COLS], "Patients": [r[b] for b in BAND_COLS]})
        fig = go.Figure(go.Bar(x=bands["Band"], y=bands["Patients"]))
        fig.update_layout(title="Waiting-time bands (this month)", height=320, margin=dict(t=50, b=10))
        rt.plotly_chart(fig, use_container_width=True)

        sp = service_table(df[df["trust_code"] == code], month, min_list=0, exclude_other=False)
        sp = sp.sort_values("at_risk_12_18", ascending=False)
        st.dataframe(pd.DataFrame({"Specialty": sp["specialty"], "Waiting list": sp["waiting_list"],
                                   "% within 18w": sp["pct_within_18w"] * 100, "Waiting 12-18w": sp["at_risk_12_18"],
                                   "To treat for 92%": sp["treat_to_reach_92"]}),
                     use_container_width=True, hide_index=True,
                     column_config={"% within 18w": st.column_config.NumberColumn(format="%.1f%%")})

# ---------------- Tab 4: what-if ----------------
with tab4:
    st.write("Pick a service and test a scenario. This is an illustration: it ignores new referrals and all other "
             "patient flows.")
    pool = cells_all.sort_values("at_risk_12_18", ascending=False).head(300)
    if pool.empty:
        st.warning("No services match the sidebar settings.")
    else:
        pool = pool.assign(label=pool["trust_name"] + " - " + pool["specialty"])
        choice = st.selectbox("Service (top 300 by patients waiting 12-18 weeks)", pool["label"].tolist())
        row = pool[pool["label"] == choice].iloc[0].to_dict()
        c1, c2 = st.columns(2)
        treated = c1.slider("Extra patients treated (leaving the over-18-week group)", 0,
                            int(max(row["over_18w"], 1)), 0)
        breach = c2.slider("Share of the 12-18 week group that crosses 18 weeks", 0, 100, 0) / 100
        res = what_if(row, treated, breach)
        m1, m2, m3 = st.columns(3)
        m1.metric("Now", f"{row['pct_within_18w']:.1%}")
        m2.metric("Scenario", f"{res['new_pct']:.1%}", f"{res['change_pp']:+.1f} pp")
        m3.metric("To treat to reach 92% (today)", f"{int(row['treat_to_reach_92']):,}")
        st.caption(f"{int(res['breaching']):,} patients cross 18 weeks; {int(res['treated']):,} treated; "
                   f"new list size {int(res['new_list']):,}.")

# ---------------- Tab 5: about ----------------
with tab5:
    st.markdown("""
**Source:** NHS England, Consultant-led Referral to Treatment (RTT) Waiting Times, monthly full-extract files,
incomplete pathways, Sep 2025 - Aug 2026. Aggregate, non-identifiable statistics.

**Definitions**
- *% within 18 weeks*: pathways waiting up to 18 weeks / all waiting pathways. NHS Constitution standard: 92%.
- *Waiting 12-18 weeks*: pathways waiting more than 12 and up to 18 weeks.
- *To treat for 92%*: patients who must leave the list for the service to reach 92%, assuming they come from the over-18-week group.
- *Risk tier*: High = top 10% by patients at risk (or top 10% by share with above-median volume); Medium = top 25% on either; Low = rest.

**Known limits**
- Some trusts did not submit in some months; trust codes can merge (North Bristol is combined with Bristol NHS FT).
- The 2.7-point jump between Feb and Mar 2026 is visible in NHS England's own series; its cause is not in the data.
- A patient can be on more than one pathway.
- The forecast column (latest month only) comes from a simple model that is only a few per cent better than "same as last month".
""")