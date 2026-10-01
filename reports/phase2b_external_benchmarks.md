# Phase II-B external benchmarks

These datasets never merge with or scale into reference-plant measurements.

## UCI Steel: real separate plant

Frozen clean 35,040 quarter-hour observations, corrected interval-start/end convention. Outer train Jan–Aug, validation Sep–Oct, test Nov–Dec remains unchanged. Validation inner chronology: September model selection, October interval calibration. Daily midnight origins and 96 direct horizons; all observed usage history ends by origin. Target Usage_kWh (kWh/15min), not scaled simulated-plant kW. Exact features: load_lag_1, load_lag_2, load_lag_4, load_lag_96, load_past_4_mean, load_past_4_std, load_past_96_mean, load_past_96_std, seasonal_naive, horizon_slot, target_hour, target_weekday, target_shift, target_sin, target_cos. Excludes same-slot CO2/reactive power/PF and all Load_Type/day-status target descriptions. Seasonal naive and last value compared with train-only Ridge and LightGBM.

| model | validation_MAE | test_MAE | test_RMSE | WAPE |
| --- | --- | --- | --- | --- |
| last_value | 17.344 | 21.244 | 37.134 | 0.85412 |
| lightgbm | 10.279 | 10.759 | 18.577 | 0.43254 |
| linear | 14.375 | 15.013 | 21.454 | 0.60361 |
| seasonal_naive | 12.604 | 14.363 | 26.662 | 0.57747 |

Selected lightgbm; held-out interval coverage 77.083%, upper coverage 94.655%. No neural benchmark was added: the tabular day-ahead pipeline is the qualified scope. Real-plant nonstationarity/holiday shifts can impair calibration; these are diagnostics, not changes to simulated calibration.

![UCI real-data forecasts](phase2b/uci.png)

## AI4I: external synthetic machine-state snapshots

10,000 independent snapshots; fixed seed-42 stratified outer 70/15/15 manifest preserved. Its validation 1,500 rows split stratified into 750 selection and 750 calibration rows. Target Machine failure preserved. Inputs ONLY: Type, Air temperature [K], Process temperature [K], Rotational speed [rpm], Torque [Nm], Tool wear [min]. UDI, Product ID, source row id and TWF/HDF/PWF/OSF/RNF are excluded. Machine-state type gets train-fitted one-hot encoding; numeric processing fitted on training only.

| model | PR_AUC | ROC_AUC | Brier |
| --- | --- | --- | --- |
| lightgbm | 0.81398 | 0.96811 | 0.012511 |
| linear | 0.43069 | 0.90034 | 0.024666 |

Selected lightgbm; calibrated held-out PR-AUC 0.81398, ROC-AUC 0.96811, precision 0.82927, recall 0.66667, F1 0.73913, Brier 0.01262, selection threshold 0.55. Confusion matrix [TN,FP;FN,TP]: [[1442, 7], [17, 34]]. Reliability bins and raw/calibrated scores in external/ai4i/metadata.json. Only a small number of positive calibration snapshots exists; probability estimates are correspondingly uncertain.

AI4I evaluates current machine-state classification, not reference-plant predictive maintenance, chronological degradation or days-ahead warning. D1 simulated day-ahead risk is a separate experiment with separate artifacts/features/labels. No AI4I mapping is used to claim real mill/pump lead-time validation.
