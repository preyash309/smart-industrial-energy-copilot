# Phase II-D matched-condition replay summary

**Decision-loop milestone: ACHIEVED for independently checked simulated operating changes. Failed original plans remain unreleasable.**

All quantities are simulated reference-plant outcomes. DIGITAL-TWIN-REALIZED uses physical truth only in segregated evaluation. OPTIMIZER-PREDICTED remains separate. SYNTHETIC-TARIFF is 4/8/12 Rs/kWh, not a Punjab/PSPCL bill. SYNTHETIC-PRACTICE is the existing loss-40 intervention, not a validated shop-floor recommendation. No EXTERNAL-BENCHMARK is used in replay or as a plant outcome. No field savings, emissions, fuel prices or maintenance benefits are claimed.

## Architecture and exact origin

The frozen V1.1 source has no origin snapshot or rolling-dispatch API. Separate replay/compatible_v111.py is a versioned replay-compatible layer copied from the protected engine. Its checked diff adds day-scoped uniform practice and exact rolling-feed admission only. All original physical equations, exogenous draws, sensor models, ratings/yields/calibration and invariant validation remain unchanged. It never clips feed, postpones a heat or reduces an order. Default six tables, summary and scenario manifest match the frozen engine and historical seed-42 artifact exactly. Additional-seed defaults are also compared to the original engine. The original simulator, analytics, models and optimizer source/artifacts remain immutable.

The replay recreates the full 30-day Jan-5 trajectory with the same seed/config. Random arrays depend on horizon length: a shortened seven/eight-day simulation would change multiple IF marks and observation tapes. Controls affect only Jan-12 00:00 to Jan-13 00:00. All six pre-origin table hashes and opening stock are compared; scenario SHA256 and individual weather/charge/delay/wear/repair/noise/missing/glitch tapes are hashed before decisions. Inventory is 50 t. Wear is calendar-driven, temperature algebraic, and V1.1 has no persistent thermal state or runtime-driven wear counter to initialize. This preserves all represented state; it cannot prove realism of absent dynamics.

Archived normal/synthetic central/conservative plans are represented with exact heat/practice/rolling controls. Uniform practice is mapped from the frozen public prediction contract and scoped to the origin day, never applied retroactively. Mixed per-heat modes fail closed. Requested feed uses opening inventory only and must fit actual mill/RHF capacity and repair availability. Exact controls do not mean exact predicted power or completion: original stochastic physical energy, delays, half-power and repairs remain independent judges. No original-plan reoptimization is performed. Additional seeds receive their own legal completed-public history and one central/conservative normal/synthetic solve each, through the unchanged typed PredictionService and optimizer. Optimizer assumptions are not replaced with future faults.

## Primary seed 42: original archived plans

| case | physical status | MWh | IF SEC | bars t | peak kVA | closing stock t | QC known meter Rs | complete physical evaluation Rs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0 | physically_valid | 106.7393 | 651.2630 | 118.5600 | 6479.8042 | 50.0000 | 779500.5444 | 790884.0252 |
| S1 | physically_valid | 106.7395 | 651.2630 | 118.5600 | 6481.1620 | 50.0000 | 764368.8286 | 776025.8825 |
| S2 | physically_valid | 104.1393 | 631.2630 | 118.5600 | 6481.1620 | 50.0000 | 779279.8080 | 780484.0252 |
| S3 | replay_infeasible | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable |
| conservative_normal | physically_valid | 106.7395 | 651.2630 | 118.5600 | 6481.1620 | 50.0000 | 764368.8286 | 776025.8825 |
| conservative_synthetic | physically_valid | 104.1395 | 631.2630 | 118.5600 | 6481.1620 | 50.0000 | 745968.5634 | 757626.5771 |

| case | OPTIMIZER-PREDICTED MWh | DIGITAL-TWIN-REALIZED MWh | predicted synthetic Rs | realized physical evaluation Rs |
| --- | --- | --- | --- | --- |
| S1 | 106.3723 | 106.7395 | 774581.76 | 776025.88 |
| S3 | 103.7744 | failed | 739368.94 | failed |
| conservative_normal | 109.8282 | 106.7395 | 799065.13 | 776025.88 |
| conservative_synthetic | 107.2242 | 104.1395 | 780626.28 | 757626.58 |

Every valid case independently passes full-run mass/electricity/fuel accounting, exact piecewise IF integration/demand/cooling, clock/cardinality, actual availability/capacity/windows, inventory, production, quality flags and control adherence. Reported heat starts and every rolling feed are compared to the requested plan. No partial heat-only approximation is used for these admitted plans. Checks and maximum accounting errors live with each evaluation. IF utilization is cycle occupied time /24h; rolling utilization is feed / (8 t/h ×24h); active-slot runtime separately counts any active quarter hour.

## Central versus conservative and failures

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

## Independently reconstructed timing root causes

| seed | case | conflicting heat | previous heat | duration overrun min | physical fault evidence |
| --- | --- | --- | --- | --- | --- |
| 42 | S3 | D007_H12 | D007_H12 | 0.467294563 | lid|charge_bad |
| 201 | S3 | D007_H09 | D007_H08 | 1.183353583 | superheat|charge_bad |
| 201 | conservative_synthetic | D007_H10 | D007_H09 | 0.5580609 | half|charge_bad |
| 202 | S3 | D007_H06 | D007_H05 | 0.53039745 | lid|charge_bad |
| 203 | S3 | D007_H04 | D007_H03 | 0.167536067 | lid|charge_bad |
| 204 | S1 | D007_H09 | D007_H08 | 0.617671117 | superheat|lid|charge_bad |
| 204 | S3 | D007_H04 | D007_H03 | 0.592803617 | lid|charge_bad |
| 204 | conservative_normal | D007_H09 | D007_H08 | 0.617671117 | superheat|lid|charge_bad |
| 205 | S3 | D007_H03 | D007_H02 | 0.56870855 | lid|charge_bad |
| 206 | S1 | D007_H05 | D007_H04 | 9.1161926 | half |
| 206 | S3 | D007_H05 | D007_H04 | 11.7161926 | half |
| 206 | conservative_normal | D007_H05 | D007_H04 | 9.1161926 | half |
| 206 | conservative_synthetic | D007_H05 | D007_H04 | 6.7161926 | half |
| 207 | S3 | D007_H06 | D007_H05 | 1.167925217 | superheat|charge_bad |
| 208 | S1 | D007_H03 | D007_H02 | 4.979316117 | half |
| 208 | S3 | D007_H03 | D007_H02 | 7.579316117 | half |
| 208 | conservative_normal | D007_H03 | D007_H02 | 4.979316117 | half |
| 208 | conservative_synthetic | D007_H03 | D007_H02 | 2.579316117 | half |
| 209 | S1 | D007_H07 | D007_H06 | 1.76670355 | superheat|charge_bad |
| 209 | S3 | D007_H02 | D007_H01 | 1.081396783 | superheat |
| 209 | conservative_normal | D007_H07 | D007_H06 | 1.76670355 | superheat|charge_bad |
| 210 | S1 | D007_H01 | D007_H00 | 7.7556074 | half|charge_bad |
| 210 | S3 | D007_H01 | D007_H00 | 10.3556074 | half|charge_bad |
| 210 | conservative_normal | D007_H01 | D007_H00 | 7.7556074 | half|charge_bad |
| 210 | conservative_synthetic | D007_H01 | D007_H00 | 5.3556074 | half|charge_bad |

Overruns are computed from retained actual heat timestamps and the original requested next start/day end, not solver slacks. Half-power and combined charge/lid/superheat losses physically extend powered duration. No MILL/PMP failure occurs inside this January-12 window for the declared seeds; this experiment therefore does not establish repair-window robustness. Five-minute rounding leaves normal central/conservative reservations identical; conservative synthetic increases reservation but still fails four additional seeds.

S0 and normal S1 have the same modeled primary IF energy and powered-duration requirements. Shifted load timing and rolling wear exposure change site trajectories. The reduced twin assigns IF losses by seed/day/ordinal rather than start hour, so success does not establish field invariance to shifting. Completed-attempt error metrics are censored by the first abort and cannot be read as whole-day interval coverage. No diagnostic is fitted back into the frozen model.

Primary normal central/conservative start/rolling controls are identical because both duration quantiles round to the same five-minute reservation. Thus their realized energy/cost/idle time are identical despite different predicted coefficients. Central synthetic S3 finishes its last heat 0.47 min beyond midnight; it is retained with a partial evaluation-only heat trace and no full-day savings metric. Conservative synthetic succeeds for the original primary scenario. p90 is empirical, not a joint safety guarantee. Robustness below includes all attempted seeds; improvement distributions are explicitly conditional on physically valid pairs.

| case | valid/attempted | feasible | kWh reduction % valid pairs | physical cost reduction % valid pairs | lower cost % all seeds |
| --- | --- | --- | --- | --- | --- |
| S1 | 5/10 | 50.0% | mean -0.0001; median -0.0001; range [-0.0002, -0.0001] (n=5) | mean 1.3394; median 1.6687; range [0.0822, 2.2032] (n=5) | 50.0% |
| S3 | 0/10 | 0.0% | no valid pairs | no valid pairs | 0.0% |
| conservative_normal | 5/10 | 50.0% | mean -0.0001; median -0.0001; range [-0.0002, -0.0001] (n=5) | mean 1.3394; median 1.6687; range [0.0822, 2.2032] (n=5) | 50.0% |
| conservative_synthetic | 6/10 | 60.0% | mean 2.4354; median 2.4340; range [2.4160, 2.4582] (n=6) | mean 3.6792; median 3.6938; range [2.7426, 4.5412] (n=6) | 60.0% |

| seed | mode family | central status | conservative status | actual idle h central/conservative | actual cost Rs central/conservative |
| --- | --- | --- | --- | --- | --- |
| 42 | normal | physically_valid | physically_valid | 1.2172 / 1.2172 | 776025.8825 / 776025.8825 |
| 42 | synthetic | replay_infeasible | physically_valid | failed / 1.7372 | failed / 757626.5771 |
| 201 | normal | physically_valid | physically_valid | 1.0274 / 1.0274 | 784173.4073 / 784173.4073 |
| 201 | synthetic | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 202 | normal | physically_valid | physically_valid | 1.2123 / 1.2123 | 776899.4805 / 776899.4805 |
| 202 | synthetic | replay_infeasible | physically_valid | failed / 1.7323 | failed / 758500.2087 |
| 203 | normal | physically_valid | physically_valid | 1.4131 / 1.4131 | 769621.2494 / 769621.2494 |
| 203 | synthetic | replay_infeasible | physically_valid | failed / 1.9331 | failed / 751221.9018 |
| 204 | normal | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 204 | synthetic | replay_infeasible | physically_valid | failed / 1.6608 | failed / 763289.8598 |
| 205 | normal | physically_valid | physically_valid | 0.9816 / 0.9816 | 781573.3565 / 781573.3565 |
| 205 | synthetic | replay_infeasible | physically_valid | failed / 1.5016 | failed / 763174.0481 |
| 206 | normal | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 206 | synthetic | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 207 | normal | physically_valid | physically_valid | 1.2235 / 1.2235 | 775724.6390 / 775724.6390 |
| 207 | synthetic | replay_infeasible | physically_valid | failed / 1.7435 | failed / 757325.2992 |
| 208 | normal | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 208 | synthetic | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 209 | normal | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 209 | synthetic | replay_infeasible | physically_valid | failed / 1.4234 | failed / 761718.1587 |
| 210 | normal | replay_infeasible | replay_infeasible | failed / failed | failed / failed |
| 210 | synthetic | replay_infeasible | replay_infeasible | failed / failed | failed / failed |

## Attribution, tests and handoff

| case vs S0 | kWh reduction | energy reduction % | physical synthetic Rs reduction | physical cost reduction % | QC-known meter Rs difference |
| --- | --- | --- | --- | --- | --- |
| S1 | -0.146775 | -0.000138 | 14858.142702 | 1.878675 | 15131.715789 |
| S2 | 2600.000000 | 2.435841 | 10400.000000 | 1.314984 | 220.736477 |
| S3 | unavailable | unavailable | unavailable | unavailable | unavailable |
| conservative_normal | -0.146775 | -0.000138 | 14858.142702 | 1.878675 | 15131.715789 |
| conservative_synthetic | 2599.766400 | 2.435622 | 33257.448103 | 4.205098 | 33531.981066 |

Full primary central attribution bridge: incomplete; do not infer combined benefit. Exact paired quantities are in primary/paired_comparison.json.

Tests: {'exit_code': 0, 'passed': 194, 'prior_tests': 163, 'replay_tests': 31, 'summary': '194 passed in 274.82s', 'command': 'PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider'}. Protected upstream: {'status': 'PASS', 'protected_files': 936}. Same-plan byte replay: reproducibility.json. Frozen default regression: default_regression.json plus each seed's evidence. Ten predeclared seeds 201–210 are disjoint from the predictive corpus 101–125; multi-seed status: completed. No cherry picking or forecast recalibration.

Machine-readable outputs: replay/optimizer_v1/experiment.json, robustness.json, evaluation_split_manifest.json, failure_analysis.parquet; primary/evaluation per-case controls, matched manifest, predicted result, physical verification, six simulator tables, tariff ledger, heat/load comparisons or retained failure. Full evidence cannot turn a failed original plan into an approved operating recommendation. This verifier is ready for a later separately authorized propose/replay/revise stage; no such loop, LLM/agent or dashboard is implemented.
