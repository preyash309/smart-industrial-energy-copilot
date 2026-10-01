# Phase II-E robust and adaptive scheduling

All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.

E0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.

Frozen upstream integrity: {'status': 'PASS', 'protected_files': 1826}. E0 seed-42 four-case metrics/status match exactly; every 201–210 normal/synthetic central/conservative outcome also matches frozen Phase II-D. No frozen upstream file was changed.

Fresh development: [1001, 1002, 1003, 1004, 1005, 1006]; validation: [1101, 1102, 1103, 1104]; final regression: [201, 202, 203, 204, 205, 206, 207, 208, 209, 210]. All policy calibration uses only six fresh development days. Policy selection preceded validation; the final protocol records design/config/source and completed-validation hashes before final regression. Final outcomes never select parameters. No predictive model or simulator calibration changed.

| strategy | development valid/attempted | validation valid/attempted | final valid/attempted | final conditional kWh | final conditional synthetic Rs | replans |
| --- | --- | --- | --- | --- | --- | --- |
| E0 | 1/6 | 0/4 | 0/10 | unavailable | unavailable | 0 |
| E1 | 5/6 | 3/4 | 6/10 | 104154.500 | 759204.913 | 0 |
| E2 | 6/6 | 2/4 | 5/10 | 104055.697 | 751305.127 | 0 |
| E3 | 1/6 | 2/4 | 5/10 | 103705.911 | 732978.283 | 120 |
| E4 | 6/6 | 4/4 | 10/10 | 104029.870 | 744789.175 | 120 |

Architecture: frozen PredictionService → shared-decision scenario MILP → commit one heat and rolling commands as slots begin → unchanged-physics execution prefix → publish completed heat/closed readings → remaining-horizon MILP. Every completed operational trace is independently replayed through frozen replay/compatible_v111.py with matched full30-day conditions and all physical checks. Incomplete/failed plans remain unreleasable.

Policy: {'end_margin_min': 5, 'minimum_buffer_min': 0, 'uncertainty_buffer_fraction': 0}. Five-minute candidate discretization left fewer than five reserve minutes under the selected scenario envelope. The successor uses one-minute heat-start resolution, retaining the fixed quarter-hour plant/accounting clock. On development, a five-minute reserve cost about 0.3975% more than zero; larger reserves and extra uncertainty buffers were not selected. This is a combined scenario/grid/reserve/adaptive policy comparison, not a causal claim that buffering alone produced the change.

Tests: {'command': 'PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider', 'exit_code': 0, 'full_suite': '229 passed in 113.49s (0:01:53)', 'latest_component_tests': '29 passed in 21.68s; final artifact acceptance: 6 passed in 6.33s', 'passed': 229, 'robust_tests': 35, 'upstream_tests': 194}. Three initial concurrent development solves exhausted host memory; their partial plans/logs/failure records remain under development_resource_failures/. Later solves use a deterministic 1000-node serial budget and at most two experiment workers. A checked feasible incumbent is not labelled optimal unless HiGHS proves optimality.

Artifacts: replay/robustness_v1 includes initial and each-step plans, state/prediction/schedule histories, replay results, every failure, comparisons, matched-reference attribution, design/source/config/split hashes and this release manifest. No LLM, model retraining, automatic maintenance, tariff alteration or online weight learning is present.
Final E4: 10/10 physical passes, 120 replans, mean 104029.870 kWh/day, IF SEC 630.405 kWh/t, plant intensity 877.445 kWh/t, synthetic cost 744789.175 Rs/day. Mean observed duration MAE 2.148 min, bias 0.449 min, p90 exceedance 0.108, realized end reserve 11.215 min, realized-minus-initial finish -1.993 min. Absolute feasibility improvement over E0 is 100.0 percentage points; relative improvement is undefined with zero E0 passes. E4 versus E0: 0 paired feasible seeds, mean cost delta unavailable% and mean energy delta unavailable kWh; E4 versus E1: 6 paired feasible seeds, mean cost delta -1.992% and mean energy delta -0.103 kWh; E4 versus E2: 5 paired feasible seeds, mean cost delta -1.072% and mean energy delta 0.022 kWh; E4 versus E3: 5 paired feasible seeds, mean cost delta 1.340% and mean energy delta 0.151 kWh. These are conditional comparisons; failed cases remain in the feasibility denominator and cannot supply a complete-day cost.


Created files: src/energy_copilot/robust/ (contracts, scenario construction, robust MILP, independent remaining/scenario checkers, state projection, controller, evaluation and integrity gates); scripts/phase2e.py and phase2e_release.py; robustness_v1/split/schema and upstream-protection configs; test_robust_scheduling.py and test_robust_release.py; usage/changelog/diff documents; five phase2e reports, comparison plot and replay/robustness_v1 release. Existing upstream source/artifact files were not edited.

Limitations: six development and four validation runs, one matched calendar working day per seed, and ten final seeds; no rare-event safety certification. Fixed reference physics retains algebraic thermal behavior and calendar-based degradation. AUX cannot be refreshed intraday through the frozen API. Availability remains the externally declared calendar; health probabilities do not automatically create availability changes. Day-7 experiments do not validate maintenance/outage scheduling. Alternative triggers, multi-heat/fixed-time commitments and online residual correction remain optional extensions. The one-minute planning grid is part of the successor policy, so reserve/scenario/replanning effects are not individually isolated. Node-limited incumbents may have an optimality gap. The loss-40 practice remains synthetic.
