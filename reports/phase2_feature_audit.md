# Phase II-A feature and availability audit

**PASS — all exit gates.** {"diagnostic_candidates": "PASS", "feature_reproducibility": "PASS", "hidden_truth_evaluation_only": "PASS", "historical_baselines": "PASS", "noisy_energy_reconciliation": "PASS", "phase1_unchanged": "PASS", "predictor_boundary": "PASS", "public_mass_accounting": "PASS", "tests": "48 passed", "time_availability": "PASS"}

Features are built exclusively from public `readings`, a strict selection of heat-register fields, public production registers and public clock/calendar/opening-balance metadata. Feature building does not read events or hidden tables. Separate evaluation code runs only after construction and writes under `evaluation/`; it cannot supply values to operator KPIs, historical baselines or diagnostics. Phase-I files and simulator source remain hash-identical to the protected manifest.

## Availability contract

- Meter/sensor/state intervals: `[interval_start, interval_end)`; values post at `interval_end + configured delay`.
- Heat log outcomes: end time, duration, energy/SEC, tapped/billet/charge masses, tap temperature and chemistry post conservatively at `end_time + delay`. Charge has no independent pre-heat posting timestamp in this data and is excluded from pre-heat inputs.
- Pre-heat expectation/context: only prior heat outcomes or meter intervals published by `start_time`; completed previous heat at exactly the next start is legal under ideal zero-delay posting.
- Production/yard reports: publish at eight-hour shift end plus delay. Slot inventory is last reported at/before slot START, not a latent instantaneous balance.
- Slot lag/rolling values: shift before rolling; each column carries the preceding observation publication time. A positive delay makes a lag unavailable if its source publishes after origin, even when its row timestamp appears earlier.
- Daily aggregates: publish at day end plus delay. Runtime is slot occupancy; repair downtime is a range based on observable state. No hidden failure timing is used.

`feature_schema.yaml` documents each column's type, unit, nullability, role, source, range and permitted tasks. `feature_availability.yaml` repeats the full per-column legal availability. `select_predictors`/`load_predictors` deny unsupported columns/tasks and mask any input whose publication time exceeds its forecast origin. They return `inputs_available_at <= forecast_origin`. Outcomes/diagnostics/labels cannot be automatically selected as energy predictors. Identifiers remain join keys, never model measurements.

## Task allowlists

`heat_energy`: calendar, previous completed heat SEC/duration, prior historical expectations and fully completed meter context. Excludes current kWh/SEC, residual, duration, heat end, output/charge mass, tap temperature and chemistry.

`slot_load_at_start`: known calendar, previously published inventory/output registers and strictly prior load/sensor lags/windows. Excludes all present-slot power/energy/PF/state/sensors. `slot_next_load`: completed present-slot observations plus backward context, usable at interval end for a later target. `asset_next_day_risk`: completed-day observed metrics at day close; no failure labels or true wear. Raw glitch-contaminated totals and row-quality labels are audit metadata, excluded from that allowlist.

## Adversarial checks and reproducibility

Tests independently recompute SEC/ratios/mass and noisy feeder accounting; mutate future meter data and current-heat outcomes; verify earlier/current forecast predictors are unchanged; inspect every lag/window; validate backward heat-to-slot joins; exercise five-minute posting delay; reject hidden columns/outcomes/evaluation tables; check null/QC fallback semantics; and compare regenerated Parquet/schema/availability bytes. The original B01 regression suite still passes; RHF zone/flue remain independently noisy, with no ratio-derived severity column added.

Evaluation-only files: `heat_targets.parquet`, `slot_targets.parquet`, `heat_labels.parquet`, `events.parquet`, `time_split_manifest.parquet`, `physical_validation.json`. Chronological heat/load splits purge outcome windows crossing a boundary and incomplete final targets. They are not predictors. Maintenance labels and model training are absent; later cycle-aware validation must keep failure cycles separated.

## Retained limitations

Zero-delay log posting is an explicit analytical assumption, not evidence about lab/ERP latency. Only shift-close inventory/output is available; true 15-minute mass states are never exposed. Public quality metadata invalidates all numeric channels on a glitch-flagged row because channel identity is not supplied; this lowers coverage conservatively. Invalid/missing sensor values are not filled from future or latent values. Empirical uncertainty ranges are not calibrated, and rules indicate candidates rather than true simulator faults. The 30-day/limited-failure horizon cannot establish field reliability or forecasting accuracy.

No simulator, physical parameters, calibration, fault generation or observation code was modified. No ML fitting, optimiser, savings, tariff or carbon model was added. Full checks and source/protection hashes accompany `analytics_v1`.
