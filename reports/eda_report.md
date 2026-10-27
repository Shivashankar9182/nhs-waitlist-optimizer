Exploratory Data Analysis Report: NHS Waiting Lists (RTT), Sep 2025 to Aug 2026
Illustrative student capstone project (AI-Powered NHS Waiting List & Appointment Optimization Platform). Not an official NHS system. Uses NHS England open, aggregate statistics only.
1. Purpose and summary
This report describes what the data shows before any modelling. The main points:
• The national waiting list is flat at about 7.0 to 7.3 million pathways, and the share waiting up to 18 weeks is far below the 92% standard (65.2% in August 2026).
• Performance stepped up by 2.7 points in March 2026 and then plateaued.
• Trusts vary enormously, from about 50% to about 91% within 18 weeks, and none of the 141 large trusts meets the standard.
• About 1.13 million patients (15.9% of the list) are waiting 12 to 18 weeks, so they are exposed to breaching within about six weeks unless treated.
• Month-to-month changes for a single service are noisy, so a forecasting model improves only slightly on "same as last month" (see the model card).
2. Data and provenance
Item
Detail
Source
NHS England, Consultant-led Referral to Treatment (RTT) Waiting Times, monthly full-extract CSV files
Part used
Incomplete pathways (patients still waiting at month end)
Period
September 2025 to August 2026, 12 months
Files
12 monthly files; September 2025, December 2025 and March 2026 are the revised versions
Size of master dataset
about 42,900 rows (month x trust x specialty), 546 trust codes, 23 specialties
Records
URLs and access dates in data/SOURCES.md
All data is aggregate and non-identifiable. No patient-level data was used.
3. Data preparation and quality
The full steps are in the data dictionary and cleaning log. The decisions that affect the findings:
• Dropped NHS's own total rows (code C_999) to avoid double counting.
• Dropped pathways for non-English commissioners (NONC), which NHS England leaves out of all published figures.
• Merged trust code RVJ (North Bristol) into RA7 (Bristol NHS Foundation Trust), because RA7's list rose by about 44,000 in July 2026 when RVJ's roughly 42,000 disappeared.
• Built a "same trusts every month" panel that keeps 97.1% of volume, for comparisons that are not distorted by trusts entering or leaving.
Check against the source: March 2026 totals 7,014,835 pathways in this dataset, against NHS England's published 7,014,879 (not including estimates). The difference is 44 pathways.
Known gaps in the source data (from NHS England's press notices and this analysis):
• Sheffield Teaching Hospitals did not submit data for the whole period (about 91,300 pathways at its last submission in June 2025), so national totals are slightly understated. NHS England's headline figures include estimates for it.
• Torbay and South Devon stopped reporting from April 2026, University Hospitals Plymouth from July 2026 and Northampton General from August 2026.
• One trust (RF4) has no row for November 2025.
• Optegra UK's reporting split into separate site codes from March 2026. These are small volumes.
4. Findings
4.1 The national waiting list is flat, and the standard is far away
The waiting list stayed between 7.01 and 7.30 million pathways, with the high in October 2025 and the low in March 2026. The share waiting up to 18 weeks rose from 61.7% to 65.2%, still about 27 points below the 92% standard.
Month
Waiting list
% within 18 weeks (all trusts)
% within 18 weeks (same trusts)
Sep 2025
7,296,893
61.75
61.51
Oct 2025
7,304,189
61.70
61.48
Nov 2025
7,159,010
61.64
61.48
Dec 2025
7,199,624
61.45
61.23
Jan 2026
7,155,958
61.43
61.25
Feb 2026
7,124,952
62.54
62.40
Mar 2026
7,014,835
65.29
65.18
Apr 2026
7,093,502
64.95
64.83
May 2026
7,153,655
65.56
65.42
Jun 2026
7,147,562
65.83
65.67
Jul 2026
7,131,685
65.30
65.23
Aug 2026
7,158,164
65.21
65.04
Figure 1: reports/figures/01_national_trend.png (waiting list and % within 18 weeks, all trusts and same trusts, with the 92% line).
The "same trusts" line runs about 0.1 to 0.3 points below the all-trusts line, so changes in who reports matter a little but do not change the story.
4.2 There was one step change, then a plateau
The share within 18 weeks rose 2.75 points between February and March 2026 (62.5% to 65.3%), then stayed between 64.9% and 65.8%. NHS England's own published series shows the same step, so it is not an error in this pipeline. The cause is not in the data. February to March 2025 moved only from 59.2% to 59.8% in NHS England's series, so the step does not look seasonal.
The jump was broad. Every specialty improved, from +1.4 points in Trauma and Orthopaedics to +4.4 points in General Internal Medicine, with Respiratory Medicine, Cardiology, Dermatology and Gastroenterology all above +3.3. In the same month the number of patients waiting over 18 weeks fell by about 234,000 while the whole list fell by only about 110,000. A pathway cannot move from "over 18 weeks" back to "within 18 weeks", so the long waiters left the list. That fits treatment, clinical validation or removals, but the data cannot say which.
Figure 2: reports/figures/02_march_jump_by_specialty.png (change in % within 18 weeks, Feb to Mar 2026, by specialty).
4.3 Specialties differ in size and performance
Figure 3: reports/figures/03_specialties_latest.png (waiting list and % within 18 weeks by specialty, August 2026).
In August 2026, Trauma and Orthopaedics has the largest list (842,785 pathways, 61.1% within 18 weeks), followed by Ophthalmology (621,164, 72.2%), Ear Nose and Throat (588,730, 56.7%) and Gynaecology (584,339, 59.6%). Several large groups are "Other" catch-all categories, which are hard to act on.
4.4 Trusts vary widely, and none of the large ones meet the standard
Of the 141 trusts with at least 5,000 pathways, none reaches 92%. The best is Midlands Partnership University NHS Foundation Trust at 90.7%. The lowest are Mid and South Essex NHS Foundation Trust (50.4%) and University Hospitals Sussex NHS Foundation Trust (52.6%), a spread of about 40 points.
Lowest 5 (5,000+ pathways)
Waiting list
% within 18 weeks
Mid and South Essex NHS FT
165,234
50.4%
University Hospitals Sussex NHS FT
118,139
52.6%
Omnes Healthcare Ltd
14,240
53.2%
Fitzwilliam Hospital
6,459
53.7%
East Kent Hospitals University NHS FT
85,362
55.4%
Highest 5 (5,000+ pathways)
Waiting list
% within 18 weeks
Midlands Partnership University NHS FT
10,166
90.7%
Sussex Community Dermatology Service
20,045
86.0%
Cora Health MSK
24,720
85.5%
Moorfields Eye Hospital NHS FT
42,010
84.6%
Northumbria Healthcare NHS FT
39,285
83.6%
Figure 4: reports/figures/04_trust_variation.png (distribution of % within 18 weeks, and backlog size against performance).
Bigger backlogs tend to do worse, but only loosely: the correlation between log backlog size and % within 18 weeks is -0.43. Moorfields is large and performs well. The top of the list is mostly community and specialist providers. This is not a causal finding.
4.5 Most trusts improved over the year
For trusts present in all 12 months, the median change in % within 18 weeks from September 2025 to August 2026 was +3.1 points, and 80% improved. Most of that is the March step.
Figure 5: reports/figures/05_trust_change.png (change in % within 18 weeks by trust).
4.6 Where patients are closest to breaching
The waiting-time bands show how many patients are about to cross the 18-week line. In August 2026, 1,133,192 patients (15.9% of the list) had waited more than 12 and up to 18 weeks, across 2,805 services (trust and specialty pairs with at least 100 pathways) in 480 trusts. These patients are exposed to breaching within about six weeks unless treated. This is exposure, not a forecast that they will breach.
Three points stand out:
• Volume is not the same as performance. Moorfields Ophthalmology has the most patients in the band (6,639) but is at 84.6% within 18 weeks, while University Hospitals of Derby and Burton Trauma and Orthopaedics has 2,488 in the band and is at 49.0%.
• Two kinds of problem. Mid and South Essex is at 50.4% within 18 weeks but has only 12.5% of its list in the 12 to 18 week band, and University Hospitals Sussex is at 52.6% with 13.5%. Most of their shortfall is patients who have already passed 18 weeks. Manchester University and King's College have higher shares in the band (16.3% and 17.1%) with better current positions. The data shows the pattern but not the cause.
• Trauma and Orthopaedics dominates by specialty, with 136,241 patients in the band (16.2% of its list). Cardiology has the highest share among the large specialties (17.3%) and Dermatology the lowest (14.3%).
The watchlist ranks services, never individual patients, and is not for clinical prioritisation.
5. Implications for modelling
• After March 2026 the national figure moves by less than a point a month, so "same as last month" is a hard baseline nationally.
• Individual trust and specialty percentages move about 2.3 points a month at random, which limits how well any model can do.
• The March 2026 step should be kept out of training or flagged. Training on it made the model worse on later months.
• The share of patients waiting 12 to 18 weeks was the most useful predictor, which matches the mechanism.
• The model card gives the results: about 5% better than "same as last month" in the final setup.
6. Limitations
• Only 12 months of data, so seasonal patterns can be called indicative but not proven.
• Some trusts did not report in some or all months, so national totals are slightly understated.
• A patient can be on more than one pathway.
• Aggregate data cannot show why numbers moved or which patients were affected.
• Comparisons between trusts reflect case mix and recording practice as well as performance.
7. Reproducing this report
Run build_master.py, validate_master.py and check_coverage.py, then notebooks/eda_national.py, which saves the five figures to reports/figures and a summary table to reports/eda_national_summary.csv. Run src/models/breach_watchlist.py for section 4.6.