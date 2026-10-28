Model Card: Next-Month 18-Week Performance Forecast (v1)
Illustrative student capstone project (AI-Powered NHS Waiting List & Appointment Optimization Platform). Not an official NHS system. Built on NHS England open, aggregate statistics.
1. Model details
Item
Detail
Name / version
baseline_v1
Type
Tabular regression, gradient boosting (scikit-learn HistGradientBoostingRegressor)
Developed
October 2026, by one student, as a portfolio project
What it predicts
Next month's percentage of waiting pathways that have waited up to 18 weeks, for one trust and specialty
How
Predicts the change from the current month, then adds it to the current value
Settings
max depth 4, learning rate 0.05, 300 iterations, random seed 42
Preprocessing
Numeric features standardised; specialty one-hot encoded
Files
models/baseline_v1.joblib and models/baseline_v1_metadata.json
Code
src/models/train_baseline.py (training), src/models/run_ablations.py (comparisons)
2. Intended use
Primary use: to demonstrate an end-to-end forecasting workflow, and to add one secondary column ("model forecast change") to the dashboard watchlist that prompts a closer look at a service.
Intended users: students, reviewers and a simulated NHS Trust digital transformation panel.
Out of scope (do not use for):
• Any decision about an individual patient, including clinical prioritisation or triage.
• Performance management, league tables, funding or targets for a named trust.
• Official forecasting or reporting of any kind.
• Presentation as an NHS product.
3. Data
Source: NHS England, Consultant-led Referral to Treatment (RTT) Waiting Times, monthly "full extract" CSV files, incomplete pathways, September 2025 to August 2026 (12 months). The September 2025, December 2025 and March 2026 files are the revised versions. All data is aggregate and non-identifiable. Download URLs and dates are in data/SOURCES.md.
Preparation (see the data dictionary and cleaning log):
• Kept incomplete pathways only.
• Dropped NHS's own total rows (specialty code C_999) to avoid double counting.
• Dropped pathways for non-English commissioners (code NONC), which NHS England leaves out of its published figures. After this, March 2026 matches the official figure within 44 pathways (7,014,835 against 7,014,879).
• Merged trust code RVJ (North Bristol) into RA7 (Bristol NHS Foundation Trust) after the merger pattern in July 2026.
• Used a balanced panel: only trust and specialty pairs present in all 12 months. This keeps 97.1% of waiting-list volume.
• Ignored cells with fewer than 100 pathways, because their percentages are very noisy.
Split by time (no shuffling):
Set
Target months
Rows
Training
Nov 2025 to May 2026, excluding Mar 2026
16,365
Test (held out)
Jun to Aug 2026
8,180
The March 2026 target month is left out of training because the national figure stepped up 2.7 points between February and March 2026 (62.5% to 65.3%), a one-off change that is not expected to repeat.
4. Features
• Current percentage within 18 weeks
• Log of the waiting list size
• Share of the list in each waiting-time band: 0-6, 6-12, 12-18, 18-26, 26-52 and 52+ weeks
• Last month's change in percentage within 18 weeks
• Last month's percentage change in list size
• A flag for target months from March 2026 onward
• Specialty
Only information from the current and previous month is used, so nothing from the future leaks into a prediction.
5. Performance
Errors are in percentage points of the percentage within 18 weeks, on the held-out months June to August 2026. The baseline to beat is "same as last month".
Final setup (March 2026 excluded from training):
Measure
Same as last month
Model
Mean absolute error
2.283
2.167
Gain

+0.116 points (about 5%), 95% interval +0.095 to +0.139
Gain weighted by list size

+0.064 points
What was tried (same test months):
Setup
Gain vs same as last month (points)
95% interval
Result
A. Trained on all months
+0.022
-0.002 to +0.048
No real gain; worse when weighted by size
B. Drop the March 2026 break from training
+0.116
+0.095 to +0.139
Small, clear gain
C. Only cells with 500+ pathways
-0.053
-0.076 to -0.031
Model worse
D. Weight training rows by list size
-0.043
-0.066 to -0.023
Model worse
E. B, C and D combined
+0.078
+0.062 to +0.094
Small gain
F. Trust level (specialties added together)
-0.132
-0.214 to -0.047
Model worse
G. Trust level, break dropped
-0.033
-0.105 to +0.035
No gain
Important: setup B was chosen after comparing these setups on the test months, so its gain is optimistic. The intervals treat each trust and specialty cell as independent, which they are not, so they are narrower than they should be.
Results from the first run (setup A), for reference:
Model
Mean error
Root-mean-square error
Weighted error
Same as last month
2.283
3.607
1.613
Same plus average drift
2.314
3.620
1.656
Ridge regression
2.313
3.453
1.793
Gradient boosting
2.261
3.433
1.728
By test month in that run, gradient boosting had a mean error of 2.21 against 2.29 in June, 2.43 against 2.42 in July, and 2.14 against 2.14 in August.
Which inputs mattered most (setup A, gradient boosting): the share of the list waiting 12 to 18 weeks was clearly first (importance 0.00188), ahead of the share waiting 18 to 26 weeks (0.00050), the change in list size (0.00042), the change in percentage (0.00033) and the current percentage (0.00021). This supports the idea that patients close to the 18-week line drive next month's result, although the effect is small.
By specialty (setup A): the model helped least, and was worse than the baseline, for Other - Mental Health Services (3.93 against 3.57), Oral Surgery (2.47 against 2.21) and Other - Medical Services (1.64 against 1.57). It helped most for Neurosurgery (2.78 against 2.98), and also for Elderly Medicine and Plastic Surgery (each about 0.16 points better).
6. Limitations
• Only 12 months of data, and about six training target months, so the model has little to learn from and seasonal patterns cannot be checked.
• A structural break in March 2026. The model is trained to ignore it and has not been tested on a second break.
• Small improvement. Gains of about 5% over "same as last month" are modest, and monthly changes for a single trust and specialty are noisy.
• Missing trusts. Sheffield Teaching Hospitals did not submit data in the period, and Torbay and South Devon, University Hospitals Plymouth and Northampton General stopped reporting in later months. The balanced panel excludes them, so the model has not seen them.
• Selection after seeing test results, as described above.
• Aggregate data. A patient can be on more than one pathway, and the data cannot show why numbers moved.
• Not validated by the NHS or any clinician.
7. Ethical considerations and risks
• The data is aggregate and non-identifiable. The model describes services, never individual patients, and must not be used to decide who is treated first.
• Differences between trusts partly reflect their case mix, size and how they record data, so a low forecast does not mean poor care.
• A forecast could be misused to rank or blame trusts. The dashboard labels the forecast as secondary and explains its limits.
• Errors are not spread evenly across specialties (see section 5), so users should look at the specialty before relying on a forecast.
8. Still to do
• Check performance across regions (ICBs) as the project plan requires, and report any region where the model is much worse.
• Rerun the saved model's final metrics and confirm they match section 5.
• Retest when more months are available, ideally with a clean test period that was not used to pick the setup.
9. How to reproduce
1. Download the monthly files with src/pipeline/download_rtt.py and unzip them into data/raw.
2. Run build_master.py, then validate_master.py and check_coverage.py.
3. Run src/models/train_baseline.py to train and save the model, and src/models/run_ablations.py to repeat the comparison.