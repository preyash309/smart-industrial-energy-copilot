# Phase II-D forecast-error and domain-shift diagnostics

All quantities are simulated reference-plant outcomes. DIGITAL-TWIN-REALIZED uses physical truth only in segregated evaluation. OPTIMIZER-PREDICTED remains separate. SYNTHETIC-TARIFF is 4/8/12 Rs/kWh, not a Punjab/PSPCL bill. SYNTHETIC-PRACTICE is the existing loss-40 intervention, not a validated shop-floor recommendation. No EXTERNAL-BENCHMARK is used in replay or as a plant outcome. No field savings, emissions, fuel prices or maintenance benefits are claimed.

| case | target | n | MAE | RMSE | bias actual-p50 | p90 exceedance |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | AUX_observed_QC | 95 | 1.2398 | 1.6063 | 0.2470 | 0.12631578947368421 |
| S1 | AUX_physical | 96 | 0.5197 | 0.7954 | 0.1065 | 0.010416666666666666 |
| S1 | MAIN_selected_mode | 96 | 73.7962 | 195.0103 | 15.2996 | n/a |
| S1 | heat_duration | 13 | 1.2558 | 1.6241 | -0.0381 | 0.0 |
| S1 | heat_energy | 13 | 110.0360 | 136.8487 | 21.9509 | 0.0 |
| conservative_normal | AUX_observed_QC | 95 | 1.2398 | 1.6063 | 0.2470 | 0.12631578947368421 |
| conservative_normal | AUX_physical | 96 | 0.5197 | 0.7954 | 0.1065 | 0.010416666666666666 |
| conservative_normal | MAIN_selected_mode | 96 | 168.2872 | 385.7452 | -128.6957 | n/a |
| conservative_normal | heat_duration | 13 | 1.2558 | 1.6241 | -0.0381 | 0.0 |
| conservative_normal | heat_energy | 13 | 110.0360 | 136.8487 | 21.9509 | 0.0 |
| conservative_synthetic | AUX_observed_QC | 95 | 1.2398 | 1.6063 | 0.2470 | 0.12631578947368421 |
| conservative_synthetic | AUX_physical | 96 | 0.5197 | 0.7954 | 0.1065 | 0.010416666666666666 |
| conservative_synthetic | MAIN_selected_mode | 96 | 168.6415 | 413.3177 | -128.5285 | n/a |
| conservative_synthetic | heat_duration | 13 | 1.2557 | 1.6244 | -0.0406 | 0.0 |
| conservative_synthetic | heat_energy | 13 | 110.2520 | 136.9840 | 22.2528 | 0.0 |

Heat metrics compare both quantiles with true physical outcomes; public heat-counter noise is separately available in simulation/heats.parquet. AUX_physical and AUX_observed_QC are reported separately: near-perfect physical AUX error reflects deterministic synthetic structure, while observed noise/missingness remains. MAIN is constructed controlled + AUX, never a MAIN forecast added twice. MAIN errors compare the selected planning mode; conservative p90 can overpredict energy. Piecewise actual peak is compared against the MILP bound; averaging cannot hide a demand violation.

Failed attempts keep completed heat comparisons (not full accepted-day metrics). The primary S3 final-day failure is a duration forecast miss plus tight day-end scheduling, not a changed fault model. Original fixed plans remain unchanged. Stale origin-frozen history, shifted starts and rounding are evaluated prospectively here; neither these seeds nor diagnostics recalibrate the frozen models. failure_analysis.parquet records valid-case residual diagnostics and all unreleasable attempts; per-seed heat/load comparison Parquets retain error-by-slot/heat for independent analysis. No claim of universal domain robustness follows from the successful subset.

| seed | case | status | cause | reason |
| --- | --- | --- | --- | --- |
| 42 | S3 | replay_infeasible | duration underprediction | D007_H12 cannot complete daily target within working day: end 1440.47 min |
| 201 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 201 | conservative_synthetic | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 202 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 203 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 204 | S1 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 204 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 204 | conservative_normal | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 205 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 206 | S1 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 206 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 206 | conservative_normal | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 206 | conservative_synthetic | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 207 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 208 | S1 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 208 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 208 | conservative_normal | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 208 | conservative_synthetic | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 209 | S1 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 209 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 209 | conservative_normal | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 210 | S1 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 210 | S3 | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 210 | conservative_normal | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
| 210 | conservative_synthetic | replay_infeasible | duration underprediction | Schedule has overlapping heat or wrong working day |
