# Data Dictionary & Cleaning Log

**Source:** NHS England, Consultant-led Referral to Treatment (RTT) Waiting Times, "Full CSV data file" for each month, Sep 2025 – Aug 2026 (12 months). Aggregate, non-identifiable statistics. URLs and access dates are in `data/SOURCES.md`.

## 1. Master dataset: `data/processed/rtt_master.csv`

One row per **month × trust code × specialty**, Incomplete Pathways only (patients still waiting at month end).

| Column | Type | Meaning |
|---|---|---|
| month | date | Reporting month (first day of month) |
| trust_code | text | NHS provider code. **Use this as the key, never the name** |
| trust_name | text | Latest name used by that code |
| icb_name | text | Provider's parent Integrated Care Board (latest) |
| specialty_code | text | Treatment function code (e.g. C_130) |
| specialty | text | Treatment function name |
| waiting_list | int | Incomplete pathways at month end (a patient can be on more than one pathway) |
| within_18w | int | Pathways waiting up to 18 weeks (sum of the 0–1 … 17–18 week bands) |
| over_18w | int | Pathways waiting more than 18 weeks |
| pct_within_18w | float | within_18w / waiting_list (blank if waiting_list = 0) |

Derived files:
- `rtt_balanced.csv`: only trust/specialty pairs present in all 12 months. Use for time-series modelling.
- `national_kpis.csv`: national monthly totals from `validate_master.py`.

## 2. KPI definitions

| KPI | Definition |
|---|---|
| Waiting list size | Sum of incomplete pathways |
| % within 18 weeks | within_18w / waiting_list. **NHS Constitution standard: 92%** |
| Gap to standard | pct_within_18w − 0.92 |
| Breach count | over_18w (pathways waiting more than 18 weeks) |

## 3. Cleaning log

| # | Decision | Reason |
|---|---|---|
| 1 | Kept only `RTT Part Description = Incomplete Pathways` | Waiting-list KPIs use incomplete pathways. Admitted, non-admitted and new-period parts are out of scope for v1 |
| 2 | Dropped treatment function `C_999` (Total) rows | NHS's own total rows; keeping them double-counts |
| 3 | Dropped commissioner `NONC` rows | Non-English commissioners. NHS England leaves these out of every published figure, so dropping them makes totals match official tables (~31k pathways in Aug 2026) |
| 4 | Summed over commissioners to provider × specialty | Model and dashboard work at provider level |
| 5 | Merged trust code **RVJ → RA7** | North Bristol stopped reporting after Jun 2026 and RA7 (Bristol NHS FT) rose by ~44k in Jul 2026 against RVJ's ~42k list. Evidence is from the data pattern, so confirm against NHS announcements before publishing |
| 6 | Keyed all trust-level work on `trust_code`; kept latest name | 6 codes changed name during the period |
| 7 | Built `rtt_balanced.csv` (trust/specialty present in all 12 months) | Avoids false changes from trusts entering/leaving; keeps ~96.6% of volume |

## 4. Known data issues (from NHS England press notices)

| Issue | Effect |
|---|---|
| **Sheffield Teaching Hospitals (RHQ)** submitted no data for the period (listed as missing in the Sep 2025 – Aug 2026 notices checked). Its last submission was Jun 2025, about 91,300 pathways | National waiting list is understated by roughly that amount in every month |
| **Torbay and South Devon (RA9)** missing from Apr 2026 (listed in the May, Jun and Aug 2026 notices) | Drop in coverage from April |
| **University Hospitals Plymouth (RK9)** and **Northampton General (RNS)** listed as not submitting for Aug 2026; absent from our data from Jul 2026 (RK9) and Aug 2026 (RNS) | National totals for Jul/Aug 2026 are understated |
| **Trust RF4** has no row for Nov 2025 | To check against the Nov 2025 notice |
| **Optegra UK (NNH)** last appears Feb 2026; individual Optegra site codes appear from Mar 2026 | Looks like reporting split into per-site codes. Small volumes |
| **Step change Feb → Mar 2026**: % within 18 weeks 62.5% → 65.2% (official series 62.6% → 65.3%) | Real in official data, not a pipeline error. Treat as a structural break in modelling |

NHS England publishes national figures **including estimates for missing trusts**. Ours exclude them, so national totals will differ slightly from NHS headline numbers (and from `RTT Overview Timeseries`). Reconcile against the "not including estimates" tables.

## 5. Reconciliation check

| Month | Our total | NHS official (excl. estimates) | Note |
|---|---|---|---|
| Mar 2026 | _fill in after rebuild_ | 7,014,879 | Should now be within ~0.1% |