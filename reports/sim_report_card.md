# Phase-I simulator report card

**Physical and baseline gates: PASS. Same-seed replay: PASS. Temporal similarity: partial; lag-4 divergence explicitly retained.** This is a simulated reference plant, not validated field performance. No predictive model, optimiser, dashboard or savings claim is implemented.

Seed 42; 30 calendar days, 26 working days, 338 completed heats. Sundays are off. All daily energy and coal baseline targets below refer to working days; calendar mean electricity is 92.940 MWh/day.

| Baseline metric | Result | Required envelope |
|---|---:|---|
| IF SEC, true energy / tapped liquid | 650.930 kWh/t | 640-660 |
| Heats / working day | 13.0 | 12-13 |
| Electricity / working day | 106.819 MWh | 96.9-107.1 |
| IF electricity share | 79.22% | 75-85% |
| Coal / working day | 7.994 t | 7-9 t; spec approximately 7.7 |
| Billets / working day | 123.50 t | 123.5 configured; spec approximately 120 |
| Bars / working day | 118.56 t | 118.56 configured; spec approximately 115 |
| Worst subslot demand | 6502.92 kVA | <=7000 |
| Yard inventory | 2.50-50.00 t | 0-200 |
| Max incomer/branch balance error | 4.55e-13 kWh | <=1e-8 |

## Physical gates

| Check | Status |
|---|---|
| shared_clock | PASS |
| electrical_balance | PASS |
| power_energy_units | PASS |
| feeder_apparent_power | PASS |
| main_vector_power | PASS |
| furnace_heat_meter_balance | PASS |
| furnace_loss_accounting | PASS |
| furnace_cycle_consistency | PASS |
| full_power_duration | PASS |
| heat_no_overlap | PASS |
| melt_balance | PASS |
| cast_balance | PASS |
| rolling_balance | PASS |
| caster_yield | PASS |
| rolling_yield | PASS |
| yard_balance | PASS |
| inventory_bounds | PASS |
| rolling_capacity | PASS |
| demand | PASS |
| pump_interlock | PASS |
| fuel_energy_balance | PASS |
| rhf_temperature | PASS |
| tap_temperature | PASS |
| latent_boundary | PASS |
| daily_billet_target | PASS |
| daily_bar_target | PASS |
| baseline_sec | PASS |
| baseline_electricity | PASS |
| baseline_if_share | PASS |
| baseline_coal | PASS |
| baseline_heat_count | PASS |

Electricity bookkeeping uses actual powered intervals; MAIN apparent demand is the vector sum of active/reactive power. Peak demand also checks conservative full-power concurrency within each slot. Casting is a zero-delay reduced-order transfer; rolling consumes opening stock before same-slot taps. Fuel ledger is coal mass times NCV, apportioned into the sourced baseline fuel requirement, added fouling loss and holding loss in internal truth. The baseline SEC includes process losses; this bookkeeping does not validate furnace wall/zone thermodynamics.

## Temporal comparison, not a fit target

| Diagnostic | Value | Predeclared envelope | Assessment |
|---|---:|---|---|
| profile_rmse | 0.8371 | 1.0 | within |
| lag_1_difference | 0.2435 | 0.25 | within |
| lag_4_difference | 0.5377 | 0.25 | OUTSIDE - documented |
| ramp_sd_ratio | 1.0161 | [0.2, 3.0] | within |

UCI lag-1/lag-4: 0.909/0.688; simulator: 0.666/0.150. Normalized ramp SD: UCI 0.509, simulated 0.518. Weekend/weekday mean: UCI 0.345, simulated 0.514; Saturday works and Sunday is off. Ramp quantiles and complete profiles are in temporal_validation.json.

Lag-4 autocorrelation is outside the declared cross-plant diagnostic envelope. A dominant single IF alternates 78 powered and 27 non-powered minutes (approximately seven slots per cycle); four-slot separation therefore often crosses charging breaks. UCI aggregates a different coils/plates plant with smoother load. Preserve the physical cycle rather than add fictitious power or fit held-out data. This discrepancy limits transfer of forecasting results; physical feasibility remains independently tested.

The default absolute ACF diagnostic tolerance was not widened after comparison. Profile/ramp similarities do not establish public-dataset model accuracy. UCI process CV is not sensor accuracy; instrument errors and missingness are separately labelled assumptions.

## Fault and measurement audit

Physical mechanism tests separately force each IF fault and check energy, duration and superheat temperature changes. Wear crosses a physical threshold before a failure/repair event, changes vibration/temperature and pump flow, and resets after replacement. Calendar-age degradation is an accelerated demonstration assumption: roughly two-week cycles imply far more than the workflow's 3-4 annual failures; no reliability or warning-lead-time claim is made. No IMS dataset was acquired or fitted.

Fault counts: [{'asset_id': 'CMP_01', 'type': 'fault', 'label': 'air_leak', 'count': 1}, {'asset_id': 'IF_01', 'type': 'fault', 'label': 'charge_bad', 'count': 153}, {'asset_id': 'IF_01', 'type': 'fault', 'label': 'half', 'count': 8}, {'asset_id': 'IF_01', 'type': 'fault', 'label': 'lid', 'count': 103}, {'asset_id': 'IF_01', 'type': 'fault', 'label': 'superheat', 'count': 57}, {'asset_id': 'MILL_01', 'type': 'failure', 'label': 'bearing_wear', 'count': 2}, {'asset_id': 'MILL_01', 'type': 'repair', 'label': 'bearing_wear_replacement', 'count': 2}, {'asset_id': 'PMP_01', 'type': 'failure', 'label': 'impeller_wear', 'count': 2}, {'asset_id': 'PMP_01', 'type': 'repair', 'label': 'impeller_wear_replacement', 'count': 2}, {'asset_id': 'RHF_01', 'type': 'fault', 'label': 'recuperator_fouling', 'count': 1}]. Bernoulli occurrence counts are checked against a three-standard-deviation finite-sample envelope, rather than an unrealistic +/-10% count gate for a rare fault over 30 days. Fault loss magnitudes come from the supplied spec; occurrence probabilities, repair duration and transfer to this plant require pilot confirmation.

Meter errors, glitches and gaps are applied after physical truth. Heat kWh/t is a noisy observed heat-counter value; baseline gates use latent heat energy. Observed branch and MAIN meters need not sum exactly. Internal latent truth, latent heat components, fault labels, events and future failure information are denied to the feature loader.

Same-seed output verification: {'readings': True, 'heats': True, 'production': True, 'events': True, 'latent_truth': True, 'latent_heats': True}. Acceptance tests include corrupted-ledger rejection, infeasible schedule rejection, future-scenario replay, observation isolation, wear/repair coupling, frozen schemas, raw hashes and split separation.

## Scope and limitations

Chemistry is an unmodelled operator-register placeholder (chem_ok=True), not a metallurgy prediction. Tap window, 98% melt yield, pump flow/limits, compressor pressure, RHF electrical/holding loads, wear curves and quick repairs are explicitly assumed. RHF temperature is controlled at 1200 C; richer thermal dynamics require measured coefficients. The 30-day export is a feasibility demonstration; annual operation and field savings remain outside Phase I.
