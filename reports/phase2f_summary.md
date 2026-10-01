# Phase II-F final evaluation and release

**PHASE II-F COMPLETE** — the frozen experiment is complete; maintenance benefit is not a release criterion. All 24 predeclared final seed/day cases and 72 strategy records are retained. Failed plans are not executable releases.

DIGITAL-TWIN-REALIZED outcomes; SYNTHETIC-MAINTENANCE interventions; SYNTHETIC-TARIFF electricity costs. Future labels and causal tables are EVALUATION-ONLY. OPTIMIZER-PREDICTED plans remain separate. Upstream EXTERNAL-BENCHMARK results are not plant-maintenance evidence.

The frozen PredictionService feeds the E4 robust/adaptive MILP and independent physical replay. F2 adds binary service windows and lexicographic robust feasibility, expected unavailable minutes, then synthetic tariff cost. No thresholds, scenario rules, service assumptions, solver logic, tariffs, production order, practice or model artifacts changed during final evaluation.

Development: [2001, 2002, 2003, 2004, 2005, 2006]; validation: [2101, 2102, 2103, 2104]; final: [2201, 2202, 2203, 2204, 2205, 2206]; days [12, 14, 26, 28], from the frozen manifest. The 201–210 evaluation seeds were not used for tuning. The 0.55 MILL/PMP thresholds, 0.75 sensor-quality gate, 15-minute service, 0.02 wear reset, six candidate times, and frozen E4 policy are unchanged. No maintenance ROI is calculated.

| Final strategy | Attempted | Physically valid | Feasibility | Production completion | No accepted continuation | Physical replay failures |
|---|---:|---:|---:|---:|---:|---:|
| F0 | 24 | 22 | 91.67% | 91.67% | 2 | 0 |
| F1 | 24 | 22 | 91.67% | 91.67% | 2 | 0 |
| F2 | 24 | 21 | 87.50% | 87.50% | 3 | 0 |

F1 is public health advice only and shares F0 controls and physical outcomes exactly. All unsuccessful continuations remain in the denominator; missing full-day outcomes are not imputed.

| Split | F0 attempted / valid / feasibility | F2 attempted / valid / feasibility |
|---|---|---|
| development | 24 / 18 / 75.00% | 24 / 21 / 87.50% |
| validation | 16 / 13 / 81.25% | 16 / 16 / 100.00% |
| final | 24 / 22 / 91.67% | 24 / 21 / 87.50% |

F2 did **not** improve final feasibility: -4.17 percentage points. Validation gains did not generalize to this small final population. Final total replans: F0 288, F2 281.

F2 made 23 selected recommendation appearances (23 eligible), across 61 eligible asset/decision observations. It committed and acknowledged execution of **16 services**: 6 MILL and 10 PMP. **14** have independently accepted full-day replay evidence; **2** completed in acknowledged prefixes whose full-day continuation failed. Prefix execution is not full-day acceptance or avoided-failure proof.

Terminal recommendation dispositions: {'executed': 16, 'replaced_by_replan': 7}. Earlier planned windows are not counted as performed services. Unselected/infeasible candidate windows are retained separately; all ledgers are EVALUATION-ONLY.

Acknowledged preventive downtime is 4.00 summed asset-hours across all attempts, of which 3.50 hours have accepted full-day replay evidence. Failed-day full totals remain unknown; the prefix services are not dropped or extrapolated.

Strict matched avoided failures: **14**. Unnecessary within 24 hours: **0 / 16 executed = 0.00%**. Undetermined: **2**, because a matched full-day replay failed. No service is claimed to lack longer-term value. Asset breakdown: {'MILL_01': {'executed': 6, 'classifications': {'averted_within_24h': 5, 'undetermined_counterfactual': 1}}, 'PMP_01': {'executed': 10, 'classifications': {'averted_within_24h': 9, 'undetermined_counterfactual': 1}}}.

Paired numerical comparison uses only **21** cases where both full physical replays passed. Each distribution below is F2 minus its own matched F0, not subtraction of unmatched successful-case averages. Percentages are means of per-pair relative changes.

| Metric | n | Mean delta | Median | Minimum | Maximum | Mean paired % |
|---|---:|---:|---:|---:|---:|---:|
| total_kWh | 21 | -34.5217 | 0.0000 | -224.9794 | 4.8778 | -0.0331% |
| IF_SEC_kWh_per_t | 21 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000% |
| plant_kWh_per_t_bars | 21 | -0.2912 | 0.0000 | -1.8976 | 0.0411 | -0.0331% |
| physical_evaluation_tariff_cost_Rs | 21 | 50.5708 | 0.0000 | -3637.4472 | 4494.6670 | 0.0075% |
| peak_piecewise_kVA | 21 | -2.3427 | 0.0000 | -14.8784 | 0.1367 | -0.0361% |

| Paired summed asset downtime | F0 hours total | F2 hours total | Mean F0 hours/day | Mean F2 hours/day |
|---|---:|---:|---:|---:|
| corrective | 2.7246 | 0.0000 | 0.1297 | 0.0000 |
| preventive | 0.0000 | 3.5000 | 0.0000 | 0.1667 |
| total | 2.7246 | 3.5000 | 0.1297 | 0.1667 |

EVALUATION-ONLY fault process over all 24 attempts: F0 {'attempted': 24, 'corrective_repair_hours': 3.5130590776358077, 'failure_occurrence_rate': 0.3333333333333333, 'fault_count': 9, 'limitation': 'Evaluation-only fault process; failed operating plans remain infeasible', 'tape_valid': 24}; F2 {'attempted': 24, 'corrective_repair_hours': 0, 'failure_occurrence_rate': 0.0, 'fault_count': 0, 'limitation': 'Evaluation-only fault process; failed operating plans remain infeasible', 'tape_valid': 24}. This is the action-aware represented fault process, including plans that failed; it is not evidence those plans completed. Corrective repairs, preventive services and their separate downtime components are not conflated. Asset-time sums can double-count simultaneous asset outages relative to wall-clock plant downtime.

The fault-process count covers the selected calendar day; strict service attribution covers the 24 hours starting at each service, which can extend into the following day. Thus 14 service-relative avoided failures must not be equated with 14 failures inside the selected-day fault-count population. Repeated days share seed histories and are not independent field failures.

All paired accepted days produced 118.56 t bars and 123.50 t billets, with zero order shortfall. Closing/minimum/maximum stock for each successful strategy case is retained in `accepted_production.parquet`. All-attempt production completion is shown above; no failed-day production is inferred from successful means.

| Paired production / stock | n | F0 mean [min, max] | F2 mean [min, max] |
|---|---:|---|---|
| bar_t | 21 | 118.5600 [118.5600, 118.5600] | 118.5600 [118.5600, 118.5600] |
| billet_t | 21 | 123.5000 [123.5000, 123.5000] | 123.5000 [123.5000, 123.5000] |
| final_inventory_t | 21 | 50.0000 [50.0000, 50.0000] | 50.0000 [50.0000, 50.0000] |
| inventory_min_t | 21 | 4.5952 [2.5000, 8.5000] | 4.8810 [2.5000, 8.5000] |
| inventory_max_t | 21 | 50.0000 [50.0000, 50.0000] | 50.0000 [50.0000, 50.0000] |

| Final failure | Strategy | Completed heats | Primary diagnostic | Terminal solver status |
|---|---|---:|---|---|
| 2202 / day 14 | F2 | 5 | solver_limit_no_accepted_continuation | solver_limit |
| 2204 / day 28 | F0 | 12 | duration_accumulation_no_feasible_continuation | infeasible |
| 2204 / day 28 | F1 | 12 | duration_accumulation_no_feasible_continuation | infeasible |
| 2204 / day 28 | F2 | 12 | duration_accumulation_no_feasible_continuation | infeasible |
| 2205 / day 26 | F0 | 12 | end_of_day_overrun | optimal |
| 2205 / day 26 | F1 | 12 | end_of_day_overrun | optimal |
| 2205 / day 26 | F2 | 12 | end_of_day_overrun | optimal |

Seed 2202/day 14 F2 completed MILL service at midnight but stopped after five heats when the maintenance continuation solve reached `solver_limit`. Its recorded generic `solver_infeasibility` label is preserved in raw evidence; the reporting diagnostic distinguishes a solver limit from proven infeasibility. F0 completed that day. The archive is not silently rerun with a longer time limit. Seeds 2204/day 28 and 2205/day 26 fail in both strategies due to remaining-window/duration problems; maintenance does not cure furnace-duration accumulation. Public execution prefixes support these diagnostics; unobserved future failures are not asserted as causes.

The separate 12-worker startup memory failure affected six launch jobs before cases ran. All logs were preserved and only missing cases were resumed at lower concurrency. Startup failures are not physical failures or extra declared seed/day cases. No successful case was rerun for performance selection.

Final audits: physical and service checker PASS for every accepted replay; posting-time/information boundary PASS; direct unaffected-exogenous-field test PASS; immutable completed decisions PASS; no-action E4 equivalence PASS. Protected upstream SHA256 files: **3530 unchanged**. Frozen design digest and config/model evidence are retained in the release manifest.

Full regression command: `$env:PYTHONPATH="src;."; .venv/Scripts/python.exe -m pytest -q`. **253 passed**, run after final evaluation; exact output is frozen as `validation_tests.log`.

Files are confined to Phase-II-F maintenance modules/configs/lock, evaluation/release/reporting scripts, tests, reports/figure/usage documentation and `replay/maintenance_v1/`. This completion step added reporting-only final distributions, terminal ledgers and validation JSON; the frozen implementation and upstream artifacts were not changed.

Release evidence: per-case plans/replans, public prediction/state/schedule histories, immutable service records, original startup logs, physical checks, strict attribution, final failures, all-attempt and paired tables, config/split/lock snapshots, data card, test log and SHA256 manifest.

![Matched development pump trace](figures/phase2f_matched_pump_trace.png)

The deterministic system is ready for Phase II-G as a **supervised simulation prototype**, not autonomous industrial deployment. A supervisor must surface failed continuations, preserve the independent physical acceptance gate and distinguish predictive advice from verified execution.

**Conclusion:** Maintenance-aware scheduling did not improve final schedule feasibility (-4.17 pp); paired corrective downtime changed from 2.7246 to 0.0000 summed asset-hours. It acknowledged 16 preventive services (14 independently full-day verified), demonstrated 14 strict matched avoided failures, and classified 0 unnecessary services (2 undetermined). Production completion changed from 91.67% to 87.50%; mean paired energy changed -0.0331% and synthetic tariff cost +0.0075%. Limits remain: synthetic wear/replacement model, small enriched evaluation population, no field-maintenance evidence, no real maintenance cost, 24-hour health model, reduced-order plant physics, and remaining heat-duration/scheduling and solver-limit failures.
