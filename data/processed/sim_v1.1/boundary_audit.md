# RHF observation boundary audit — sim_v1.1

**PASS — B01 resolved.** This is a narrowly scoped successor to the historical `reports/phase1_independent_audit.md`, whose V1.0 verdict remains unchanged.

Root cause: zone and flue measurements multiplied their true values by the identical `(1 + sensor_noise * z)` sample. The ratio cancelled that factor. Hiding `latent_fouling` by column name did not prevent exact severity recovery.

V1.1 derives two stable named `numpy.random.Generator` streams from the simulation seed through the existing SHA256-name/SeedSequence factory: `rhf_zone_temperature` and `rhf_flue_temperature`. Both tapes are generated before decisions. True zone/flue values are computed first and only observed RHF temperatures use those tapes. Existing configured relative sensor SD remains 0.005 (0.5%); no added noise, physical model change, new faults or calibration change. Existing missing/glitch processes are preserved. Independent noise prevents sample-wise cancellation while retaining statistical information about fouling.

Attack: `(1200 * observed_flue / observed_zone - 350) / 40`. Select active RHF rows with finite flue and zone within nominal +/-100 C, reproducing the audit filter without selecting on reconstruction error.

| Metric | V1.0 | V1.1 |
|---|---:|---:|
| Rows | 1655 | 1655 |
| Median absolute severity error | 5.62050406216e-16 | 0.0437856182277 |
| Maximum absolute severity error | 2.10942374679e-15 | 0.200403282142 |
| Rows with error <1e-10 | 1655 | 0 |
| Zone/flue residual correlation | 1.000000 | -0.035527 |
| Observed flue/fouling correlation | 0.482821 | 0.478445 |

Measured relative zone/flue residual SD: 0.004878 / 0.005137, consistent with the existing 0.005 scale. No new sensor-specific scale is introduced. Tests explicitly reject median error <=1e-6 or maximum error <=1e-5, require zero exact rows, independent residuals and flue/fouling correlation >0.3. The legacy artifact fails these gates, demonstrating that the regression detects the original blocker.

**PASS — public/hidden boundary.** The strict feature loader retains permitted observed columns and rejects injected latent fouling/wear, health, severity, future failure/event and fault-label columns. No future exogenous noise tape is included in public tables. Hidden tables remain internal diagnostics; labels/events are targets, not features. This tests the named algebraic attack, not a claim that noisy physical observations have no predictive information. As required, fouling still raises true flue temperature and fuel use.

**WARNING — inherited limitations unchanged.** W01-W09 from the independent V1.0 audit remain applicable, including interval-end availability, reduced RHF thermal/chemistry physics, accelerated wear, baseline output and UCI ACF discrepancies. Files are semantically separated by the loader, not protected by filesystem ACLs. No Phase-II work is included.

Evidence: `boundary_checks.json`, `seed_checks.json`, `replay.json`, `tests.json`; reproducible command: `python -m scripts.release_v11`. Configuration/hash version and scenario identity change to record the new observation model; physical exogenous sequences and accounting do not.
