# Phase II-B uncertainty report

Individual-outcome p10/p50/p90 prediction quantiles, not confidence intervals for a model mean. Residual ranks fit exclusively on calibration seeds 119–121; UCI uses October. Signed finite-sample residual ranks are added to selected point predictions; residual median defines central prediction. Nonnegative clipping preserves ordering. Load calibration is per horizon (minimum 30 observations, global fallback otherwise); heat calibration is pooled across modes, with mode coverage separately reported. No Gaussian error assumption, test recalibration or hidden physical replacement.

| task | selected | requested_interval | test_interval | requested_upper | test_upper | mean_width |
| --- | --- | --- | --- | --- | --- | --- |
| heat_energy | group_mean | 0.8 | 0.80991 | 0.9 | 0.88757 | 478.19 |
| heat_duration | group_mean | 0.8 | 0.78883 | 0.9 | 0.87981 | 6.0101 |
| load | lightgbm | 0.8 | 0.81501 | 0.9 | 0.90859 | 3.6814 |
| uci | lightgbm | 0.8 | 0.77083 | 0.9 | 0.94655 | 36.351 |

Units: heat energy kWh, duration min, simulated AUX kW, UCI kWh/15min. Detailed coverage/MAE/width by test seed, practice mode and each of 96 horizons: corresponding metadata.json grouped_test. Peak forecast error: load and external/uci metadata interval. Residual/interval plots: phase2b/heat_energy.png, heat_duration.png, load.png, uci.png. Health probabilities use sigmoid held-out calibration, with Brier/reliability evidence below and in model metadata.

| task | selected | PR_AUC | Brier | threshold |
| --- | --- | --- | --- | --- |
| health_MILL_01 | linear | 0.97201 | 0.0060338 | 0.4 |
| health_PMP_01 | linear | 0.997 | 0.0032799 | 0.45 |

Calibration observations within a run are correlated; finite-sample rank corrections do not establish iid conformal guarantees for this time-series setting. Coverage is an empirical held-out-seed diagnostic. Rare faults, long outages, alternative schedules, stale day-ahead heat context and unseen seasons can fall outside these ranges. p90 can support later risk-aware design but does not guarantee the 7,000-kVA physical constraint; independent replay/hard physics remains mandatory. No field safety/probability claims are made.


## Calibration and qualification warnings

Heat p90 upper coverage is 88.76% for energy and 87.98% for duration versus nominal 90%. UCI two-sided coverage is 77.08% versus nominal 80%, with asymmetric upper coverage 94.66%. These discrepancies remain visible; no test-data recalibration or interval widening was performed. Mill sigmoid calibration slightly worsens held-out Brier (0.00569 raw to 0.00603); AI4I likewise changes 0.01251 to 0.01262. Pump improves from 0.00542 to 0.00328. All health tasks still beat their no-skill prevalence Brier, but applying a calibrator does not prove improved calibration. Reliability plots/bins show remaining mismatch.

The selected heat group means effectively use only known practice_loss_kWh_t and proposed shift. Their 12-field strict interface preserves compatibility with the independently compared linear/LightGBM candidates; unused historical inputs do not improve the selected baseline. Ordinary prior-only historical mean baselines are also reported. Complex heat models did not qualify on selection improvement and were not promoted. Both health LightGBM models score higher PR-AUC on final test, but their small validation gain did not reach the predeclared 0.01 threshold; test outcomes did not overturn the simpler-model selection.

Near-perfect AUX forecasting reflects repeated fixed calendar and calibrated deterministic daily structure plus small observed noise in the synthetic model, not field robustness or generalization to changed operating policy/seasons. No observable regime clusters existed in analytics_v1; known shift/practice/calendar context is used, and no future regime label was invented. Individual rows within a seed are correlated; seed-wise metrics are the stability evidence, not iid precision guarantees.

predictions/test_* Parquets are evaluation artifacts that also contain actual outcomes and target timestamps. They must never be used as predictor tables or passed wholesale into the future optimizer. Consume only the typed PredictionService outputs defined in prediction_schema.yaml; it never returns actual target outcomes, actual completion times or future event labels.
