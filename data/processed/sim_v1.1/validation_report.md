# sim_v1.1 validation report

**PASS.** All 33 tests pass (28 existing Phase-I tests plus 5 B01 regression tests). See `tests.json` for the actual command/output. Validation completes before the successor freeze. No physical/configuration numeric parameter changed; only plant/package version metadata and RHF observation processes changed.

**PASS — exact baseline preservation.** Seed 42, 30 days, 26 working days, 338 heats. V1.0 and V1.1 latent truth, latent heat registers, production, events and public heats are exactly equal. All unrelated observed columns and all non-RHF readings are exactly equal. Every physical summary field is exactly equal. IF SEC 650.929960091 kWh/t; electricity 106.818967869 MWh/working day; coal 7.993855690 t/working day; bars 118.560000 t/working day. Peak conservative demand 6502.922854 kVA; independent actual peak 6502.217564 kVA. Yard 2.500000–50.000000 t. Delta for each physical KPI: zero.

**PASS — independent accounting.** Standalone ledger arithmetic adapted from the original adversarial audit imports no simulator calculation/validation functions. All 66 independent checks pass, including mass/energy/fuel, 15-minute demand, yard bounds, cooling interlock, yields/throughput and independent subslot demand/cooling reconstruction. Residuals and violation counts are in `independent_checks.json`.

**PASS — replay and fault causality.** All six Parquets are byte-identical across two contemporary seed-42 runs and scenario manifests are equal. Changed flue-stream naming cannot shift zone noise, physical state, fault labels or unrelated observations (dedicated regression). Zero observation noise leaves physics unchanged (existing regression). Physical fault effects are covered by the existing mechanism tests and identical physical/fault tables. Seeds 1–30 additionally pass independent constraints and B01 gates. Their physical metrics match the pre-patch adversarial seed results within CSV round-trip precision, with no recalibration and no rejected/censored seeds; IF SEC and plant electricity still vary between seeds.

| Additional-seed metric | Minimum | Mean | Maximum |
|---|---:|---:|---:|
| if_sec | 648.112 | 650.259 | 652.244 |
| plant_MWh | 106.459 | 106.735 | 106.991 |
| reported_peak_kVA | 6501.7 | 6503.09 | 6504.79 |
| coal_tpd | 7.99322 | 7.99346 | 7.99385 |
| bar_tpd | 118.56 | 118.56 | 118.56 |
| inventory_min | 0 | 1.71667 | 2.5 |
| inventory_max | 50 | 50 | 50 |
| recovery_median_error | 0.0397911 | 0.0417531 | 0.0439013 |
| recovery_max_error | 0.187763 | 0.222264 | 0.266235 |
| flue_fouling_correlation | 0.481311 | 0.512237 | 0.543739 |

**PASS — immutable predecessor.** Every file in `sim_v1.0`, the original audit and its evidence folder is verified unchanged before and after release. Their hashes are in `prior_evidence_hashes.json`. The exact successor config, schema, calibration, seed, runtime, source hashes, dependency lock and current source/test code hashes are snapshotted in V1.1.

**WARNING — previous warnings remain.** Baseline energy acceptance is a run mean, not an every-day envelope. Existing UCI temporal diagnostics are carried over because power is exactly unchanged; no fitting or recomputation can be attributed to this observation-only patch. Refer to the immutable original independent audit for W01-W09. The previously frozen data card's blanket independent-noise statement was not true for RHF; use the V1.1 boundary audit for corrected evidence. No optimisation, models, savings claims or unrelated warning changes.
