# UCI Steel audit

Source: supplied immutable CSV, SHA256 `9b1cee6f9cb9cd9df2b95814ca90a9a2ff15b7f5f1fba0fae3c643e82072eacc`. Real Korean plant; different size/product from this reference plant.

35,040 rows, zero missing values, duplicates or 15-minute gaps after the documented interval correction. Coverage: 2018-01-01 00:00:00 to 2019-01-01 00:00:00 exclusive. All numeric energy/reactive/PF ranges valid; NSM matches original clock time. Full ranges are in uci_steel_audit.json.

The file has 365 backward timestamp jumps: every day's 00:00 row follows 23:45 with the same printed date. Verified this pattern on all 365 days. Interpret 00:00 as next-day interval end and subtract 15 minutes for interval-start timestamps. Keep original date, source_timestamp and source_row_id. Day labels now agree with interval starts; no values removed or imputed. Midnight correction is a documented inferred convention, not supplied timezone evidence. Source time is timezone-naive Korean local clock; simulator uses separate Indian local clock.

Jan-Aug training, Sep-Oct validation, Nov-Dec test are frozen by interval-start date. Calibration uses training only. All-year EDA is descriptive; do not use its held-out insights for model selection. Repeated adjacent loads (3454 pairs), low-load periods and spikes are retained; repeated kWh alone is not a duplicate record.

- Normalized profile: weekend/weekday mean load ratio 0.349; this is operating behaviour, not evidence of avoidable waste.
- Tariff-band view: 5.2% of annual observed energy falls in the illustrative seasonal Punjab evening band; no monetary conversion or shifting/savings claim.
- Lagging PF is below 0.90 in 54.8% of rows; leading PF below 0.90 in 21.4%. These channels are distinct, not interchangeable site PF.

## Leakage boundary
CO2 is derived/rounded from same-slot energy. Both reactive-energy columns and both PF columns describe the same electrical interval and can reveal same-slot Usage_kWh through power identities. Drop them for contemporaneous prediction or use strictly past lags available before the forecast origin. Do not include Load_Type if defined from contemporaneous load. Backward-only windows, train-only scaling and forecast-horizon purging remain requirements for Phase II. No model or savings estimate is produced in Phase I.
