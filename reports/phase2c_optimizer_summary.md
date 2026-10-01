# Phase II-C optimizer summary

**PASS — C1–C5 and independent schedule release gates. OPTIMIZER-PREDICTED; no twin replay or verified savings.**

Pyomo 6.9.5 + highspy/HiGHS 1.12.0, serial deterministic seed 42, zero requested relative MIP gap. Pinned additive lock: requirements-phase2c.lock.txt (includes ply 3.11); earlier dependencies unchanged. [APPSI interface](https://pyomo.readthedocs.io/en/6.9.5/api/pyomo.contrib.appsi.solvers.highs.Highs.html), [HiGHS release](https://pypi.org/project/highspy/1.12.0/).

Horizon 2026-01-12 local midnight to midnight, 96 × 15-minute material/meter/availability slots. All candidates and forecasts generated before building a solver. Known completed history from Jan 5–11 is predicate-filtered at posting time before loading; last published shift-close inventory is 50 t. Orders remain 13 heats, 130 t liquid, 123.5 t billets, 118.56 t bars, closing stock at least 50 t. No stock drawdown funds the comparison.

## Decisions and objectives

Binary x[candidate_id] = x[heat,start,practice], furnace_on[t], pump_on[t], asset_run[asset,t]; continuous inventory[0..96] and rolling_t[0..95] (billet feed tonnes). Heat sequence preserves supplied identity order. Candidate starts use a five-minute subslot grid while all accounting and rolling remain at 15 minutes. Occupancy reserves ceil(predicted duration / start grid). With normal p50 ≈105.2 min and p90 ≈108.4 min, the strict 15-min-start policy reserves 120 min/heat and cannot fit 13 heats into 24h. That infeasibility is recorded rather than shortening a forecast or lowering output. Five-minute resolution is an explicit optimizer assumption, not a physical/configuration recalibration.

C1: feasibility objective 0, normal practice. C2: sum predicted slot kWh. C3: sum slot kWh × supplied Rs/kWh, normal practice. C4: same cost objective with explicitly supported synthetic practice_loss_40. C5: central vs conservative marginal quantiles. No weighted multiobjective, carbon/fuel objective, or maintenance scheduling. No SEC target was supplied: cap is explicitly disabled in release examples. Optional input cap is enforced; tests demonstrate a 635 cap and infeasible 500 cap without changing forecasts.

## Predicted comparison

All rows produce 118.56 t bars / 123.5 t billets and end at 50 t inventory. Synthetic tariff: offpeak 4, normal 8, peak 12 Rs/kWh; these are test inputs, not a jurisdiction-specific bill.

| Plan | MWh | IF SEC kWh/t | Synthetic cost Rs | Peak kVA bound | Yard minimum t | Reserved IF utilization |
|---|---:|---:|---:|---:|---:|---:|
| central_baseline | 106.3723 | 649.0679 | 778033.43 | 6935.927 | 0.500 | 99.3056% |
| c2_energy_normal | 106.3723 | 649.0679 | 778808.46 | 6935.927 | 2.500 | 99.3056% |
| c3_tariff_normal | 106.3723 | 649.0679 | 774581.76 | 6935.927 | 2.500 | 99.3056% |
| c4_tariff_synthetic | 103.7744 | 629.0842 | 739368.94 | 6935.071 | 6.500 | 94.7917% |
| conservative_baseline | 109.8282 | 675.2979 | 804674.70 | 6937.910 | 0.500 | 99.3056% |
| conservative_tariff_normal | 109.8282 | 675.2979 | 799065.13 | 6937.910 | 2.500 | 99.3056% |
| conservative_tariff_synthetic | 107.2242 | 655.2677 | 780626.28 | 6937.910 | 2.500 | 99.3056% |

Normal-practice tariff scheduling changes synthetic cost while leaving predicted kWh/SEC unchanged in this example. The coupled intervention changes both forecast energy and cycle time through the frozen models; no independent MILP efficiency formula was added. Comparison deltas are in plans/optimizer_v1/predicted_comparison.json. These are predicted differences, not verified savings.

## Constraints and binding evidence

Each heat exactly once; ordered nonoverlapping furnace occupancy at the configured start grid; every heat finishes within horizon; IF and all service equipment respect supplied windows/availability; full-power energy tail requires at least configured 27 nonpowered minutes; cooling ON whenever IF powered; configured cast/melt/rolling yields; billet output requirement; exact bar order (no gratuitous overproduction); mill and RHF feed capacity, mill nameplate energy limit; rolling consumes only opening stock; 97 bounded yard states and conservative intra-slot arrival upper bound; explicit closing reserve; configured RHF setpoint inside 1150–1250 C; supported practice allowlist; optional SEC cap; per-slot additive apparent-power/nameplate reserve <=7000 kVA. All are hard, with no violation-slack variables.

- c3_tariff_normal: demand slack 64.073 kVA; binding demand slots []; production slack 0.000000 t; closing inventory slack 0.000000 t; lower/upper yard binding boundaries [] / []; SEC cap absent; 39 start binaries, 2485 constraints.
- c4_tariff_synthetic: demand slack 64.929 kVA; binding demand slots []; production slack -0.000000 t; closing inventory slack 0.000000 t; lower/upper yard binding boundaries [] / []; SEC cap absent; 415 start binaries, 4805 constraints.
- conservative_tariff_synthetic: demand slack 62.090 kVA; binding demand slots []; production slack 0.000000 t; closing inventory slack 0.000000 t; lower/upper yard binding boundaries [] / []; SEC cap absent; 78 start binaries, 2732 constraints.

Full solver termination/bounds and active constraints accompany each result. Production and closing stock bind; nameplate demand has positive slack, so no claim that demand was the optimization bottleneck. Furnace reservation utilization approaches the one-day limit. No IIS/minimal infeasible subsystem is claimed.

## Approximations and handoff limitations

IF forecast energy is placed at 5-MW full power at the END of the predicted cycle; preceding time is nonpowered. This preserves forecast total energy and leaves the configured nonpowered minimum but does not reproduce every half-power/repair/delay trajectory. Heat energy remains exact under overlap integration into 15-min slots. Nameplate IF/mill/compressor reserve is used for demand, separate from average electrical energy. Additive asset apparent power upper-bounds combined P/Q apparent power by the triangle inequality; both are reported. PF is fixed to versioned configuration. AUX is the ONLY forecast component; five controlled feeders are added once. No MAIN forecast is consumed.

RHF nominal readiness and compressor loaded/idle duty retain the reference window; pump stays continuously on when available. Mill energy follows 100 kWh/t bars with configured yield/capacity. Wear/future faults, chemistry and detailed thermal dynamics are not modeled by the MILP. Equipment availability is an external planning/permissive assumption, including qualified cooling flow; a health probability cannot certify tomorrow’s availability.

Frozen V1.1 accepts arbitrary-time heat-start maps plus a GLOBAL practice setting, but not this rolling dispatch table or mixed per-heat modes. Released intervention plans use one global mode, yet an exact origin-state/rolling-policy replay adapter still needs explicit design in Phase II-D. Do not silently replay a different rolling policy or apply an intervention to earlier history and call it matched conditions. No replay has occurred here.

p90 is empirical, not a physical guarantee; individual energy/duration quantiles are not a joint calibrated safe region. Shifted/stale-history schedules remain outside Phase II-B’s separate prospective validation. Synthetic practice loss 40 is not a real shop-floor recommendation. Inherited chemistry/wear/UCI/tariff warnings remain unchanged. No demand charges/FPPAS/kVAh billing, fuel costs, emissions or verified savings.

## Health, infeasibility, tests and next phase

- MILL_01: raw 24-h failure probability 5.05625e-17, calibrated 5.3082e-21; informational only. Tests changing risks to 0.999 leave the schedule unchanged.
- PMP_01: raw 24-h failure probability 4.44371e-18, calibrated 2.65383e-18; informational only. Tests changing risks to 0.999 leave the schedule unchanged.
- strict_15_minute_reference: **INFEASIBLE**, unreleasable; No eligible in-horizon candidates under duration, availability and ordered occupancy constraints.
- excess_production: **INFEASIBLE**, unreleasable; Order 200 t bars exceeds available rolling/RHF capacity 122.88 t; Closing mass ledger -34.8333 t cannot meet reserve 50 t.
- low_demand_cap: **INFEASIBLE**, unreleasable; No feasible incumbent; inspect production, windows, stock, duration, demand and SEC constraints.
- impossible_SEC_cap: **INFEASIBLE**, unreleasable; Even unconstrained candidate SEC lower bound 628.791 exceeds explicit cap 500 kWh/t liquid.

All existing and new test results: reports/phase2c_tests.json. Deterministic C1 and cost solves, typed input serialization/reload, analytical toy optimum, independent tamper attacks, unavailable services, SEC/demand/output infeasibility, p50/p90 selection, source separation, null sensors, posting timestamps, fallback rejection and frozen hashes are tested. No model retraining or simulator/config/data modification.

New code: src/energy_copilot/optimization/{contracts,candidates,model,constraints,objective,solve,checker,baseline,explain,__init__}.py; scripts/phase2c{,_setup,_release}.py; configs/optimizer_v1.yaml and phase2c_readonly_manifest.json; requirements-phase2c.lock.txt; tests/test_optimizer_*.py; docs/phase2c_usage.md; plans/optimizer_v1; three Phase-II-C reports and aligned load/production/inventory plots. No earlier-phase source/artifact files changed.

Phase II-D receives exact orders/state/availability/tariff, origin-frozen typed predictions, model/schema hashes, solver decisions and independent-checker evidence. Next work is an explicitly compatible matched-condition replay and outcome evaluation, including handling of replay-policy gaps and forecast misses. It is not completed in Phase II-C.

![Central normal plan](phase2c/c3_tariff_normal.png)

![Conservative synthetic experiment](phase2c/conservative_tariff_synthetic.png)
