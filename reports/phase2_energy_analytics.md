# Phase II-A monitoring and energy analytics

**PASS — analytics_v1 generated from immutable sim_v1.1 public outputs.** No simulator/physical assumption/observation change, ML training, optimisation or billing/carbon calculation is included.

## Equipment electricity and utilization

| asset_id | known_kWh | raw_meter_kWh | coverage_h | peak_kVA | active_slot_h | downtime_lower_h | downtime_upper_h | known_MWh_working_day | common_feeder_share_pct |
|---|---|---|---|---|---|---|---|---|---|
| AUX | 163555.306 | 164307.246 | 716.000 | 313.439 | 720.000 | 0.000 | 0.000 | 5.970 | 5.895 |
| CMP_01 | 50407.184 | 50251.447 | 718.750 | 96.348 | 720.000 | 0.000 | 0.000 | 1.842 | 1.808 |
| IF_01 | 2188068.216 | 2191410.298 | 716.500 | 5229.730 | 529.500 | 0.000 | 0.000 | 84.156 | 78.962 |
| MAIN | 2776026.706 | 2784228.988 | 716.750 | 6569.951 | 720.000 | 0.000 | 0.000 | 106.351 | unknown |
| MILL_01 | 309846.952 | 310465.158 | 717.250 | 834.841 | 404.000 | 0.000 | 1.000 | 11.917 | 11.109 |
| PMP_01 | 45267.083 | 45122.882 | 717.000 | 79.020 | 624.000 | 0.000 | 1.000 | 1.741 | 1.630 |
| RHF_01 | 16597.364 | 16607.167 | 718.500 | 42.878 | 416.000 | 0.000 | 0.000 | 0.638 | 0.594 |

Known energy is a subtotal, not an estimate of unobserved slots. MAIN is the plant meter and is never added to its six feeders. Raw meter totals retain reported glitches/missingness; quality totals reject rows marked glitched, retain nulls, and use same-interval kW times 0.25 h only when kWh is missing and kW is valid. No future imputation or hidden physical replacement is used. Per-day shares compare identical asset/MAIN coverage; `feeder_mix_share_common_all` uses the common six-feeder denominator and sums to one. AUX is the separate public simulated feeder here; it is not silently replaced by a residual as in the deployment meter-saving proposal.

| asset_id | meter_slots | power_fallback_slots | missing_energy_slots | quality_flagged_slots |
|---|---|---|---|---|
| AUX | 2854 | 10 | 16 | 16 |
| CMP_01 | 2857 | 18 | 5 | 5 |
| IF_01 | 2850 | 16 | 14 | 14 |
| MAIN | 2853 | 14 | 13 | 13 |
| MILL_01 | 2855 | 14 | 11 | 11 |
| PMP_01 | 2846 | 22 | 12 | 12 |
| RHF_01 | 2864 | 10 | 6 | 6 |

Active-slot hours count any observed running/partial-repair interval. They are **not exact powered runtime**, especially for IF start/stop slots. Repair-only downtime is an interval bound: partial-repair records do not expose within-slot timings. Scheduled off is not assumed to be a breakdown. All daily aggregates become available at local day close.

## Production, intensity and register reconciliation

Raw/public totals: 338 heats; liquid 3380.000 t; billets 3211.000 t; bars 3082.560 t; coal known subtotal 205769.617 kg. Rolling yield 96.000%. MAIN quality-known energy 2776026.706 kWh at 99.549% coverage. Published shift-close yard stock range 2.500–50.000 t.

Normalized metrics (separate from raw totals): observed IF heat-counter SEC 651.156019 kWh/t liquid; known plant electricity 900.558856 kWh/t bars; known coal 66.752834 kg/t bars; MAIN known working-day mean 106.350662 MWh. Missing coverage prevents treating the last three as exact physical full-period totals. Independent heat and feeder counters are not forced to agree.

All public mass-register identities pass; largest residual 7.11e-15 t. Heat liquid/billet/charge totals join at completion to the proper production shift, including exact shift-end boundaries. Energy reconciliation uses 2806 of 2880 common valid slots: feeders 2720925.779 kWh versus MAIN 2720957.324 kWh; signed difference -31.546 kWh; median absolute slot discrepancy 0.434%. This is a noisy-meter reconciliation, not a failed or artificially repaired physical balance.

![Equipment energy and SEC distribution](phase2_analytics/energy_and_sec.png)

## Expected energy and heat examples

Baseline selection: prior same-shift/working-day mean once eight records exist, otherwise prior rolling-twenty mean, otherwise prior global mean after warm-up. All outcomes must have `available_at <= heat.start_time`. First eight heats have no expectation or candidate diagnosis. No present-heat outcome, fault label or future calibration row is included. Expected kWh scales expected SEC by prior historical tapped mass, never the current unknown output. Empirical 5th–95th percentiles and sample SD describe prior variability; they are not calibrated prediction intervals or best-practice/avoidable-energy estimates. Baselines adapt online and may normalize persistent poor practice.

| heat_id | actual_SEC | expected_SEC | residual_SEC | duration_min | tap_temp_C | interpretation |
|---|---|---|---|---|---|---|
| D004_H02 | 650.516 | 650.460 | 0.057 | 105.825 | 1638.554 | near historical expectation |
| D022_H04 | 651.070 | 651.230 | -0.160 | 105.226 | 1640.175 | near historical expectation |
| D026_H06 | 716.608 | 650.018 | 66.590 | 124.982 | 1689.949 | high residual candidate |
| D016_H01 | 706.720 | 651.008 | 55.712 | 123.356 | 1694.546 | high residual candidate |

These are ordinary and high-residual **observed examples**, not true good/bad fault assignments. Heat SEC mean 651.156, median 651.895, SD 17.389, range 618.882–716.608 kWh/t. 330 of 338 heats have a historical expectation.

![Expected actual and residuals](phase2_analytics/expected_actual_residuals.png)

## Production timeline and diagnostic evidence

![Plant load and published production](phase2_analytics/load_production_timeline.png)

Inventory and output are only reported per completed eight-hour shift. Slot features use the latest report published by **slot start**, with age and an opening-balance flag. Rolling output is explicitly `rolling_output_last_shift_t`, not invented slot production. No interpolation of future registers or access to latent yard/rolling state is used.

| timestamp | asset_id | source_id | rule | measured_value | expected_value | residual | confidence |
|---|---|---|---|---|---|---|---|
| 2026-01-05 15:30:00 | MILL_01 | 2026-01-05 15:15:00 | machine_power_deviation | 573.737 | 768.712 | -194.975 | low |
| 2026-01-06 05:12:43.042000550 | IF_01 | D001_H02 | high_temperature_and_energy | 669.724 | 644.310 | 25.414 | moderate |
| 2026-01-06 15:45:00 | CMP_01 | 2026-01-06 15:30:00 | compressor_mill_off_load | 85.418 | 44.942 | 40.476 | low |
| 2026-01-07 10:37:54.530444067 | IF_01 | D002_H05 | high_heat_SEC | 695.065 | 653.964 | 41.102 | low |
| 2026-01-13 07:08:57.361884205 | IF_01 | D008_H03 | long_heat | 117.000 | 105.221 | 11.779 | low |

Candidate counts: {"compressor_mill_off_load": 69, "high_heat_SEC": 11, "high_temperature_and_energy": 16, "long_heat": 9, "machine_power_deviation": 482}. Full records contain timestamp/heat or interval ID, measured/expected/residual, metric unit, JSON observable evidence, possible cause and confidence/limitations. Sustained deviations generate repeated evidence rows rather than distinct confirmed incidents. Compressor candidates require observed mill-off context; its source state is always running and cannot itself prove unloaded operation. No AUX candidate is required if observed deviations do not meet the documented threshold. Sensor flags are QC metadata, not diagnoses.

![Asset utilization](phase2_analytics/asset_utilization.png)

## Limits and next handoff

Public meters have missingness/glitches and independent noise; invalid observations remain null. Same-slot power/PF are descriptive analytics, excluded from same-slot load prediction. Chemistry is a simulator placeholder and its real lab availability is unknown; excluded from pre-heat forecasts. Ideal zero posting delay is explicitly assumed because ingestion timestamps are absent, and configured delay is enforced by the loader. The frozen reduced RHF model, calendar wear, baseline output and UCI ACF warnings are unchanged. No tariff/emission rates are executable inputs here: no cost, savings or CO2 results are generated.

The thirty-day horizon supports provisional chronological heat/load splits only, not annual seasonal validation or reliable predictive-maintenance performance claims. Cycle-aware maintenance evaluation and sufficient failure horizons belong to the next modelling stage. Use the task allowlist loader, not automatic numeric-column selection. Exit checks: {"diagnostic_candidates": "PASS", "feature_reproducibility": "PASS", "hidden_truth_evaluation_only": "PASS", "historical_baselines": "PASS", "noisy_energy_reconciliation": "PASS", "phase1_unchanged": "PASS", "predictor_boundary": "PASS", "public_mass_accounting": "PASS", "tests": "48 passed", "time_availability": "PASS"}.
