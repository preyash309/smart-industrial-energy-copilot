# Independent adversarial audit of sim_v1.0

Audit date: 2026-09-29. Frozen data: `data/processed/sim_v1.0/`. Scope: read-only audit of the existing Phase-I implementation and dataset. **No simulator, configuration, source dataset, interim dataset or frozen output was changed.** New report evidence lives under `reports/phase1_audit/`; an isolated scratch harness under `tmp/phase1_audit/` performs independent arithmetic.

## Verdict

**BLOCKER: the hidden-severity boundary is not sufficient for downstream release.** The physical accounting, frozen seed-42 constraints, provenance and replay pass. Thirty additional seeds pass the independently reconstructed hard constraints. One blocker is an exact latent-fouling-severity oracle available from two permitted observed feature columns. The audit identifies this as a leakage/observation-boundary defect under the explicit requirement that true fault severity not be exposed as downstream features. Ordinary noisy physical correlation with health is expected; exact cancellation of the observation layer is the issue here.

The frozen version remains untouched. Warnings alone do not justify unfreezing it. No fix or recalibration is applied by this audit; the blocker needs an explicit reviewed resolution before claiming the hidden boundary is safe for Phase-II feature construction.

| ID | Status | Finding |
|---|---|---|
| P01 | PASS | All frozen content/source hashes, exact config/seed, calibration and pinned runtime match; seed-42 replay is byte-identical. |
| P02 | PASS | Independent slot, heat, shift, whole-plant material and electrical/fuel accounting close within floating-point tolerance. |
| P03 | PASS | 2,880 slots satisfy demand, inventory, throughput, temperature and cooling permissives; subslot reconstruction also passes demand and IF/pump overlap checks. |
| P04 | PASS | All 30 additional fixed-config seeds return complete tables and have zero independent hard-constraint violations. |
| P05 | PASS | Injected IF losses, superheat tap temperature, half-power duty, leak power, fouling fuel/exhaust and wear-to-failure effects are present. |
| B01 | BLOCKER | Allowed RHF `temp_C` and `flue_temp_C` share the identical noise sample; their ratio reconstructs hidden `latent_fouling` to floating-point precision on 1,655 active rows. |
| W01 | WARNING | Feature timestamps mark interval starts; complete-interval meters and `repair_partial` state require availability at interval end. The loader does not enforce an as-of timestamp. |
| W02 | WARNING | The 102 MWh +/-5% check is a **run mean**, not an every-working-day bound: 8/26 frozen working days exceed 107.1 MWh. |
| W03 | WARNING | More output (130 t liquid/118.56 t bars), 16 h rolling and an added RHF electrical feeder explain most of the reference mismatch; this is not the exact 125/115 t reference plant. |
| W04 | WARNING | Wear/repair assumptions are accelerated, calendar-age based and very quick; chemistry is hard-coded true and RHF discharge temperature is imposed, not independently thermally/metallurgically validated. |
| W05 | WARNING | Superheat is in per-heat tap temperatures but absent from the powered IF 15-minute temperature channel. |
| W06 | WARNING | The lag-4 ACF difference is structural; UCI is a different process. Profile and duration-curve mismatches remain material despite similar ramp SD. |
| W07 | WARNING | Calendar/shift/schema constants and seed defaults remain in code; several configured nominal fields are descriptive only. Replay reads the live calibration path, not automatically the frozen snapshot. |
| W08 | WARNING | Half-power faults intentionally violate the normative full-power practice on 8 heats; normal-heating validation is explicitly conditional on excluding those labelled faults. |
| W09 | WARNING | Three additional seeds reach zero billet stock. This is allowed, but buffer slack is thin even though daily targets pass. |

## Independence and method

Loaded the six frozen Parquet files with pandas/pyarrow. Recomputed KPIs, mass balances, reactive/active power, availability and constraints with standalone numpy/pandas arithmetic. **No simulator calculation, validation, scenario, calibration or reporting functions are imported for those calculations.** The only simulator entry point invoked for seed execution is `simulate(config_snapshot, seed=..., days=30)`; the original validator runs naturally inside that function. Its summary is not used as audit evidence. The feature loader/schema validator are separately exercised only for boundary tests.

Used the exact frozen config, unchanged, for seed 42 and seeds 1-30. No alternate practice, schedules, probabilities, repairs or parameters were supplied. Simulation tables stay in memory; audit statistics are written to reports only. All 31 calls returned, so there is no rejected-run censoring. The scratch runner would record exceptions and incomplete outputs without suppressing the simulator's gates. Public-data diagnostics use the existing corrected UCI clean table, Jan-Aug only. Compared the reference electricity table directly against supplied Reference_Plant_Spec_v2.pdf page 6; no existing report is used as a calculation source.

### Frozen provenance and replay — PASS

- Freeze manifest mismatches: []; source-code manifest mismatches: []; runtime version mismatches: {}.
- Frozen config equals live `configs/plant_v1.yaml`; frozen calibration equals live `configs/calibration_v1.yaml`. Independent canonical config SHA256 matches `scenario_manifest.json`: `145fa6d287f2f9bbffa6977718d1b614f13163f41a883835e3d8907d275dd001`.
- Config seed, `seed.json`, scenario seed and published summary seed all equal 42. Start 2026-01-05 00:00; 30 local calendar days through 2026-02-03, end exclusive 2026-02-04; timezone Asia/Kolkata.
- Seed-42 replay result: {'readings': True, 'heats': True, 'production': True, 'events': True, 'latent_truth': True, 'latent_heats': True, 'scenario_manifest_identical': True}. All six Parquet byte hashes match the freeze, not merely two contemporary runs. Scenario manifest also matches exactly.
- Numeric summary comparisons have maximum error 0; the stored conservative peak is separately distinguished from recomputed actual piecewise peak.
- Caveat: the config references `configs/calibration_v1.yaml`. The engine reads that live path (`engine.py:167`) instead of resolving the stored `calibration_v1.yaml` next to the frozen config. They match now; a replay package must preserve/verify that dependency, not assume config+seed alone are self-contained.

## Independently recomputed frozen KPIs — PASS

| KPI | Independent result |
|---|---:|
| Working days / heats | 26 / 338 (13 each working day) |
| True IF SEC | 650.929960 kWh/t tapped liquid |
| Observed noisy heat-counter SEC | 651.156019 kWh/t |
| True plant electricity / working day | 106.818968 MWh |
| True plant electricity / calendar day | 92.940039 MWh |
| True plant electricity, 30 days | 2788201.164585 kWh |
| IF working-day electricity share | 79.218978% |
| Coal / working day | 7.993856 t |
| Liquid / billets / bars per working day | 130 / 123.5 / 118.56 t |
| Plant electric SEC, including off-day electricity | 904.508319 kWh/t bar |
| Combined electric + coal input SEC | 4739.570243 MJ/t bar |
| Slot-average / actual piecewise peak demand | 6502.217564 / 6502.217564 kVA |
| Stored conservative subslot upper bound | 6502.922854 kVA |
| Interval-end yard / conservative intraslot floor | 2.5-50 t / 0.500 t |

No tariff-rate or emissions-factor inputs are frozen as executable pricing/carbon parameters. Costs, emissions totals and savings are not independently supported by this dataset/config; no such numbers are invented in this audit.

Observed MAIN has 14 missing energy slots and 13 rows with a sensor-glitch flag. Summing observed MAIN kWh with missing values skipped gives 2784228.988 kWh, not the physical total. Its discrepancies cannot be treated as energy creation/destruction. The public heat counter is also noisy. Physics tests therefore use internal truth and reconcile it against independent heat/production registers; public noisy meters are not expected to close exactly.

### Why 106.82 MWh versus approximately 102 MWh?

| Asset | Reference MWh/day | Audited MWh/working day | Delta | Working-day share |
|---|---:|---:|---:|---:|
| IF_01 | 81.300 | 84.620895 | +3.320895 | 79.22% |
| RHF_01 | 0.000 | 0.640000 | +0.640000 | 0.60% |
| MILL_01 | 11.500 | 11.963542 | +0.463542 | 11.20% |
| PMP_01 | 1.800 | 1.748377 | -0.051623 | 1.64% |
| CMP_01 | 1.700 | 1.846154 | +0.146154 | 1.73% |
| AUX | 6.000 | 6.000000 | +0.000000 | 5.62% |
| Total | 102.300 | 106.818968 | +4.518968 | 100% |

The reference's displayed asset values sum to **102.3**, while its headline rounds to approximately 102. The actual difference is +4.518968 MWh against the displayed sum (+4.818968 against the rounded headline, +4.7245%).

- **IF: +3.320895 MWh.** Reference ~125 t liquid versus actual 130 t/day: +5*650/1000 = +3.25 MWh. Actual SEC 650.929960 adds +0.120895 MWh over 130*650; the reference 81.3 rounds 125*650/1000 = 81.25 upwards by 0.05. Together +3.25+0.120895-0.05 = +3.320895.
- **Mill: +0.463542 MWh.** Additional bars versus 115 t: (118.56-115)*100/1000 = +0.356 MWh; wear/friction adds +0.107542 MWh. Baseline output alone requires 11.856 MWh/day.
- **RHF: +0.640 MWh.** The reference daily electrical table omits the blower/pusher feeder. The simulator adds a disclosed 40 kW*16 h = 640 kWh; it is not silently charged to coal or lost from incomer accounting.
- **Compressor: +0.146154 MWh.** Healthy 85 kW*16 h +42.5 kW*8 h = 1.7 MWh/day. The leak contributes +5 kW during loaded hours (90 kW cap), +15 kW during idle hours: +200 kWh per affected working day. Nineteen of 26 working days are affected: 200*19/26 = 146.153846 kWh/day.
- **Pump: -0.051623 MWh.** The stochastic efficiency curve starts below the 75 kW nameplate, rises with impeller wear, and removes electrical operation during repair; average becomes 1.748377 MWh instead of 1.8. This is a difference between disclosed simulation assumptions, not a savings claim.
- **AUX: unchanged at 6 MWh.** The normalized daily profile redistributes its power in time and preserves mean 250 kW.

**W02:** Individual working days range 105.307808-108.397031 MWh. Eight exceed 107.1 MWh; none are below 96.9. The existing acceptance code tests only the run mean (`validate.py` baseline electricity gate). Its report labels the number as a mean, so the statement is numerically supported; it must never be restated as every day being within +/-5%.

## Independent material and energy reconstruction

No duplicated per-asset plant-state columns are summed across assets: MAIN is used once for slot-level mass, independently checked against per-heat inputs and per-shift output. Electricity sums the six consuming feeders and excludes MAIN from that sum.

Material totals in tonnes:

```
Initial yard 50 + charge 3448.979591837
  = finished bars 3082.560000000
  + melt loss 68.979591837
  + caster loss 169.000000000
  + rolling loss 128.440000000
  + final yard 50.000000000.

Charge 3448.979591837 * 0.98 = liquid 3380.000000000
Liquid 3380.000000000 * 0.95 = billets 3211.000000000
Rolled billets 3211.000000000 * 0.96 = bars 3082.560000000
```

Reconstructed each tap's liquid/charge/billet arrival into the containing 15-minute slot using the heat end timestamp. Cumulative stock is opening 50 + cumulative cast billets - cumulative rolled billets. Per-shift records match independent slot sums and ending stocks. All per-slot and total material residuals meet 1e-8 t tolerance.

Electrical inputs: sum of feeders = MAIN = 2,788,201.164585 kWh. IF heat sum = IF slot meter sum = 2,200,143.265107 kWh. Independent piecewise integration of heat energies, half-power duty and timestamped pump repairs matches all IF slots; max slot error 1.36e-09 kWh. Whole IF heat/meter summation differs by only 2.79e-09 kWh.

RHF coal: 207,840.247941 kg * 22 GJ/t /1000 = 4,572.485455 GJ. Reconstructed components: baseline 4,562.188800 GJ + fouling 9.932622 GJ + repair holding 0.364032 GJ. This is correct **input-energy bookkeeping**, not an independently validated thermodynamic efficiency or enthalpy balance. IF's best/practice/fault terms also form an input-loss allocation, not a metallurgical heat-capacity model.

### Every-slot and subslot constraints — PASS for physical baseline

| Independently evaluated check | Violating records | Status |
|---|---:|---|
| asset_slot_cardinality | 0 | PASS |
| unique_asset_timestamp | 0 | PASS |
| 15_minute_clock | 0 | PASS |
| working_calendar | 0 | PASS |
| electricity_branch_to_main | 0 | PASS |
| kWh_equals_kW_times_hours | 0 | PASS |
| apparent_energy_units | 0 | PASS |
| feeder_kVA_from_P_and_PF | 0 | PASS |
| main_P_from_branches | 0 | PASS |
| main_kVA_vector_sum | 0 | PASS |
| main_PF | 0 | PASS |
| IF_total_heat_energy | 0 | PASS |
| IF_component_energy | 0 | PASS |
| heat_SEC | 0 | PASS |
| melt_input_from_heat | 0 | PASS |
| caster_from_heat | 0 | PASS |
| heat_to_clock_charge_t | 0 | PASS |
| heat_to_clock_liquid_t | 0 | PASS |
| heat_to_clock_billet_t | 0 | PASS |
| melt_mass | 0 | PASS |
| caster_mass | 0 | PASS |
| rolling_mass | 0 | PASS |
| caster_yield | 0 | PASS |
| rolling_yield | 0 | PASS |
| inventory_cumulative | 0 | PASS |
| inventory_interval_end_bounds | 0 | PASS |
| inventory_opening_minus_rolling_bounds | 0 | PASS |
| inventory_conservative_intraslot_upper | 0 | PASS |
| whole_plant_mass | 0 | PASS |
| coal_NCV_energy | 0 | PASS |
| coal_energy_components | 0 | PASS |
| RHF_baseline_fuel_from_bars | 0 | PASS |
| RHF_fouling_fuel | 0 | PASS |
| RHF_temperature_limits | 0 | PASS |
| IF_tap_temperature_limits | 0 | PASS |
| heat_no_overlap | 0 | PASS |
| heat_wall_duration | 0 | PASS |
| normal_IF_full_power | 0 | PASS |
| half_power_duration | 0 | PASS |
| availability_PMP_01 | 0 | PASS |
| availability_MILL_01 | 0 | PASS |
| rolling_RHF_and_mill_capacity | 0 | PASS |
| slot_cooling_interlock | 0 | PASS |
| slot_average_contract_demand | 0 | PASS |
| rated_power_IF_01 | 0 | PASS |
| rated_power_MILL_01 | 0 | PASS |
| rated_power_PMP_01 | 0 | PASS |
| rated_power_CMP_01 | 0 | PASS |
| rolling_outside_schedule | 0 | PASS |
| daily_billet_target | 0 | PASS |
| daily_bar_target | 0 | PASS |
| heats_per_working_day | 0 | PASS |
| production_register_billet_t | 0 | PASS |
| production_register_bar_t | 0 | PASS |
| production_register_rolled_billet_t | 0 | PASS |
| production_register_liquid_t | 0 | PASS |
| production_register_charge_t | 0 | PASS |
| production_register_melt_loss_t | 0 | PASS |
| production_register_cast_loss_t | 0 | PASS |
| production_register_rolling_loss_t | 0 | PASS |
| production_register_stock | 0 | PASS |
| independent_IF_piecewise_energy | 0 | PASS |
| independent_IF_powered_minutes | 0 | PASS |
| exact_piecewise_contract_demand | 0 | PASS |
| exact_piecewise_pump_interlock | 0 | PASS |
| published_peak_is_conservative | 0 | PASS |

Demand reconstruction uses P and Q from each feeder PF and `sqrt((sum P)^2+(sum Q)^2)`. Instantaneous intervals are split at slot boundaries, IF power-stage boundaries and failure/repair boundaries. Mill/pump active portions are recovered from their interval-average power and independently calculated repair availability. Maximum actual reconstructed demand is 6,502.217564 kVA; the stored 6,502.922854 kVA uses pump nameplate and is conservatively higher. The reconstruction assumes mill drive power is uniform over available portions of its slot; that is the source's reduced-order duty assumption, not a waveform claim.

The inventory lower bound also tests **opening stock minus the entire slot's rolled quantity**, before adding any same-slot tap, giving 0.5 t for seed 42. Opening stock plus same-slot arrivals stays below 200 t. Those conservative bounds prove no hidden negative stock from casting/rolling order within a slot.

For each heat, independently march the required electrical energy through rated power, the labelled 20-minute half-power phase, and zero power during pump failure intervals. All reconstructed heat ends match the register. No powered interval overlaps pump repair and flow during permitted operation remains at least 80 m3/h. Heat D028_H06 pauses **19.863334 minutes** for the 2026-02-02 pump repair and preserves its 6,425.081593 kWh; total powered duration stays 77.100979 min and wall cycle becomes approximately 123.964313 min.

Chemistry is not a validated physical constraint: all 338 `chem_ok` fields are a hard-coded placeholder (`engine.py:139`). RHF discharge temperature is prescribed as 1200 C while active; this checks its configured control assumption, not thermal dynamics. Half-power malfunction is a declared baseline exception to full-power normal practice, not proof that every melting instant meets the normative full-power rule.

## Representative aligned 48-hour trace

Window: **2026-02-02 00:00 through 2026-02-04 00:00, end exclusive**. This is the final two days of the frozen run, selected because both pump and mill fail while the working plant is operating. The plant trace aligns six equipment-state bands, power, interval-end yard stock, four material production streams and fault/failure/repair events. Inventory is plotted at interval end; electricity/production quantities belong to their labelled intervals. State colors: green running, grey off, red partial/full repair.

![Aligned 48-hour plant trace](phase1_audit/plant_trace_48h.png)

![Wear, sensor drift, repair and IF pause in the same window](phase1_audit/wear_trace_48h.png)

Observed trace: IF charging breaks repeat about every seven slots; rolling stops after its 16-hour window and stock recovers as late heats cast. Pump repair at 11:20:53 on 2 February pauses IF heating while its energy requirement is retained; mill repair at 13:00 reduces rolling availability, increases RHF holding fuel and is recovered within rolling capacity slack. End stock returns to 50 t and daily production targets pass. Inspect `trace_window.json` for all aligned events and exact timestamps.

## Injected fault audit

**P05:** labels are linked to effects, not simply appended to physically unchanged records. The source samples exogenous occurrence/practice marks first, computes each effect and then emits associated labels. This demonstrates internal causal consistency of the prescribed mechanisms; it does not identify real equipment failure physics from field data.

Selected five affected heats spread across the horizon for each IF label. Contributions below are independently inferred from the additive energy accounting, conditional on other concurrent faults. Charge loss is the residual after removing known superheat/lid/half contributions, not a private random-generator value.

| Fault | Heat | All simultaneous labels | Attributed kWh/t | Actual SEC | Tap C | Powered min |
|---|---|---|---:|---:|---:|---:|
| superheat | D000_H02 | superheat | 20.000 | 656.321 | 1690.0 | 78.759 |
| superheat | D007_H08 | superheat | 20.000 | 652.226 | 1690.0 | 78.267 |
| superheat | D011_H06 | superheat|charge_bad | 20.000 | 674.855 | 1690.0 | 80.983 |
| superheat | D019_H04 | superheat | 20.000 | 642.381 | 1690.0 | 77.086 |
| superheat | D029_H10 | superheat | 20.000 | 652.049 | 1690.0 | 78.246 |
| lid | D000_H00 | lid | 15.000 | 645.374 | 1640.0 | 77.445 |
| lid | D007_H02 | lid | 15.000 | 648.177 | 1640.0 | 77.781 |
| lid | D014_H01 | lid | 15.000 | 644.551 | 1640.0 | 77.346 |
| lid | D023_H02 | lid | 15.000 | 645.949 | 1640.0 | 77.514 |
| lid | D029_H01 | lid | 15.000 | 650.609 | 1640.0 | 78.073 |
| charge_bad | D000_H04 | lid|charge_bad | 28.165 | 671.471 | 1640.0 | 80.577 |
| charge_bad | D007_H12 | lid|charge_bad | 28.370 | 673.894 | 1640.0 | 80.867 |
| charge_bad | D015_H10 | charge_bad | 28.083 | 656.352 | 1640.0 | 78.762 |
| charge_bad | D023_H03 | lid|charge_bad | 25.061 | 670.564 | 1640.0 | 80.468 |
| charge_bad | D029_H12 | charge_bad | 27.884 | 657.551 | 1640.0 | 78.906 |
| half | D008_H03 | lid|half | 20.000 | 666.663 | 1640.0 | 90.000 |
| half | D008_H09 | superheat|half | 20.000 | 667.597 | 1690.0 | 90.112 |
| half | D016_H01 | superheat|half|charge_bad | 20.000 | 699.507 | 1690.0 | 93.941 |
| half | D019_H01 | superheat|half | 20.000 | 667.352 | 1690.0 | 90.082 |
| half | D026_H06 | superheat|lid|half|charge_bad | 20.000 | 711.042 | 1690.0 | 95.325 |

- **Superheat:** 57/338 heats; +50 K gives 1690 C versus 1640 C unlabelled; +20 kWh/t (200 kWh/heat) and +2.4 powered minutes at 5 MW. All heat-level temperature labels/effects agree. **W05:** the 15-minute powered IF `temp_C` channel is still exactly 1640 C during these heats (`engine.py:235`). Only the tap log exposes the superheat temperature; slot-level temperature detection would miss it.
- **Lid open:** 103 heats; +15 kWh/t, +150 kWh/heat, +1.8 powered minutes at rated power; labelled open windows last the configured 20 minutes. No continuous lid-temperature/position sensor is simulated.
- **Rusty/loose charge:** 153 heats; independently inferred +25.015610 to +29.980322 kWh/t. Unlabelled charge residual is exactly zero. Extra energy lengthens powered time consistently; chemical impact is not modelled.
- **Half-power malfunction:** 8 heats; reconstructed first 20 powered minutes at 2.5 MW and remaining energy at 5 MW. The 20 kWh/t loss adds 2.4 minutes of equivalent full power; partial duty adds another 10 powered minutes. Pump outages pause that duty rather than changing energy. A naive test of interval-average IF kW==5000 would incorrectly flag ordinary partial slots; the independent check uses actual reconstructed segments.

Audited **every** bearing/impeller failure (two of each, hence fewer than five exist):

| Mechanism | Failure start | Repair min | Extrapolated wear at threshold | Vibration before -> after, mm/s | Flow before -> after, m3/h |
|---|---|---:|---:|---|---|
| bearing_wear | 2026-01-19 05:19:17.689595236 | 19.872 | 0.999999999984 | 6.497 -> 1.503 | n/a |
| bearing_wear | 2026-02-02 13:00:00.135473381 | 29.768 | 0.999999999986 | 6.498 -> 1.502 | n/a |
| impeller_wear | 2026-01-19 23:58:29.976610684 | 15.422 | 0.999999999988 | 4.999 -> 1.002 | 85.004 -> 99.993 |
| impeller_wear | 2026-02-02 11:20:53.361402805 | 19.863 | 0.999999999997 | 4.997 -> 1.002 | 85.010 -> 99.992 |

Monotone pre-failure wear extrapolates to 1 at the event time, with worst error below 2e-11. Replacement resets wear and vibration; impeller flow recovers from approximately 85 to 100 m3/h. Bearing temperature rises with wear plus ambient variation. Mill friction increases its kWh per bar tonne. Pump power rises towards its nameplate as efficiency degrades; its operating flow falls. Partial repair slots use midpoint wear, so drift/reset timing is a coarse representation rather than a precise sensor waveform.

Compressor leak is one persistent episode, not multiple independent faults. Several idle-window samples across 12 Jan (unaffected), 13 Jan, 20 Jan and 1 Feb show exactly +15 kW after onset; the last is an off-day with 29.875 kW versus 14.875 healthy idle power. Loaded extra power is +5 kW because of the 90 kW cap. Pressure is fixed at 7 bar; leak signature is electrical, not a pressure-drop model.

Recuperator fouling is also one continuous episode; sampled active windows on 5, 15, 26 Jan and 3 Feb all show coal penalty proportional to severity and hotter flue gas. Severity rises to approximately 0.09 by day 30, so the actual extra fuel fraction peaks near **0.45%**, not the 5% full-severity value. The source-spec 5% mechanism is scaled, not fully reached in this horizon. The exact hidden-severity recovery from these observed channels is B01 below.

Full numerical examples for all mechanisms, including sample timestamps and effects: [fault_examples.json](phase1_audit/fault_examples.json). No counterfactual parameter changes were used in this audit.

## Public/hidden feature boundary

Direct-column boundary **PASS**: the reading-feature allowlist excludes health, severity, future-failure time, fault labels, latent columns, events and latent heat loss/duration fields. A latent-wear column injected in an in-memory copy is rejected by the existing strict schema. `load_reading_features()` returns only join keys and the 14 permitted observed fields. Heat labels and full-horizon events are public **target/evaluation** tables, not predictor inputs. The simulator builds physical state before applying measurement noise and does not mutate material/energy state from measurement errors.

### B01 — BLOCKER: exact hidden severity through observation-noise cancellation

For active RHF rows, true zone temperature is fixed at 1200 C and true flue temperature is `350 + 40 * latent_fouling`. `engine.py:265-285` applies zone-temperature observation noise and then uses the **same** temperature noise draw for the flue sensor. Thus:

```
observed_zone = 1200 * (1 + sensor_noise * z)
observed_flue = (350 + 40 * true_fouling) * (1 + sensor_noise * z)
recovered_true_fouling = (1200 * observed_flue / observed_zone - 350) / 40
```

The RHS uses only allowed `temp_C`, allowed `flue_temp_C` and versioned config constants. Selected finite active rows using observed zone temperatures near their operating range, without filtering on hidden severity. **All 1,655 selected rows recover latent fouling to <=2.11e-15 absolute error** (median 5.62e-16). Truth is used only to score the recovery, not as an input to it. Nine other active rows have missing/glitched zone readings; that does not protect the 99.46% recoverable majority. Every derived recovered-severity feature would be the prohibited internal truth rather than a noisy health estimate.

This is stronger than ordinary measured signals correlated with a fault: the entire intended observation uncertainty cancels. Existing name-only latent checks cannot detect this shortcut. This audit therefore cannot confirm that true fault severity cannot enter downstream feature tables. [Recovery proof](phase1_audit/severity_recovery_proof.csv), [boundary audit](phase1_audit/boundary_audit.json).

Suggested resolution for a **later authorized version**, not applied here: model distinct flue/zone sensor error streams and validate that allowed feature transformations do not reproduce internal severity exactly; avoid treating deterministic fouling age as a general machine-health benchmark. If exact coupled physical measurements are intentionally accepted instead, explicitly revise the data-boundary requirement and any validation claim before downstream use.

### W01 — WARNING: as-of time is not enforced

The table timestamp is an interval-start label, while kWh, aggregated operating state and partial repair state describe the entire next 15 minutes. Example: at row timestamp 2026-01-19 23:45, pump state already says `repair_partial`, but failure starts at 23:58:29.9766, **809.98 seconds later**. Similarly, the mill 05:15 row contains the 05:19 failure. This is legitimate retrospective interval data **available at interval end**, not a feature available at interval start. There is no explicit `available_at` or as-of filter in the loader. No trained/persisted ML feature table exists yet, so an actual forecast leakage path is not demonstrated; treating these values as start-time-known would create one. Backward-window wording alone is insufficient without a declared forecast origin.

Future exogenous tapes are internal and generated before decisions. Their full contents are not added to readings; scenario hashes are audit metadata, not features. The seed/config and full-horizon event table make the synthetic world replayable; they must remain experiment/target metadata rather than predictor inputs. Hidden files are co-located and governed semantically by the loader, not by operating-system access controls. This is acceptable for a research repository, but not an absolute security guarantee.

## Thirty additional seeds: no parameter changes or recalibration

Seeds **1-30**, excluding frozen seed 42, each use the same frozen config and 30-day horizon. All 30 return complete tables; none is rejected, none has an accounting residual above 1e-8 and none violates any independent hard constraint. These are 30 sample worlds, not proof of feasibility for every possible RNG realization.

| Metric over 30 independent runs | Mean | Sample SD | Min | P05 | Median | P95 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| IF SEC (kWh/t liquid) | 650.2593 | 0.8876 | 648.1124 | 649.2413 | 650.1504 | 651.7528 | 652.2437 |
| Plant MWh/working day | 106.7352 | 0.1161 | 106.4585 | 106.6013 | 106.7235 | 106.9315 | 106.9911 |
| Peak slot kVA | 6502.4954 | 0.8159 | 6500.9745 | 6501.2874 | 6502.5297 | 6503.7565 | 6504.4772 |
| Peak reconstructed subslot kVA | 6502.4954 | 0.8159 | 6500.9745 | 6501.2874 | 6502.5297 | 6503.7565 | 6504.4772 |
| Stored conservative peak kVA | 6503.0902 | 0.8589 | 6501.6971 | 6501.8177 | 6503.0237 | 6504.3897 | 6504.7860 |
| Liquid t/working day | 130.0000 | 0.0000 | 130.0000 | 130.0000 | 130.0000 | 130.0000 | 130.0000 |
| Billet t/working day | 123.5000 | 0.0000 | 123.5000 | 123.5000 | 123.5000 | 123.5000 | 123.5000 |
| Bar t/working day | 118.5600 | 0.0000 | 118.5600 | 118.5600 | 118.5600 | 118.5600 | 118.5600 |
| Interval-end minimum stock (t) | 1.7167 | 1.0560 | 0.0000 | 0.0000 | 2.5000 | 2.5000 | 2.5000 |
| Interval-end maximum stock (t) | 50.0000 | 0.0000 | 50.0000 | 50.0000 | 50.0000 | 50.0000 | 50.0000 |
| Conservative intraslot stock floor (t) | 0.4500 | 0.6067 | 0.0000 | 0.0000 | 0.5000 | 1.6000 | 2.5000 |
| Coal t/working day | 7.9935 | 0.0002 | 7.9932 | 7.9932 | 7.9935 | 7.9938 | 7.9938 |
| Hard-constraint/balance violation count | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| Days outside individual 102 MWh +/-5% | 7.5333 | 2.3742 | 4.0000 | 5.0000 | 7.0000 | 11.5500 | 15.0000 |
| superheat heat count | 72.5000 | 9.8111 | 57.0000 | 59.4500 | 73.0000 | 88.1000 | 92.0000 |
| lid heat count | 100.8333 | 6.1425 | 89.0000 | 91.4500 | 101.5000 | 111.3000 | 114.0000 |
| charge_bad heat count | 134.4667 | 9.0924 | 116.0000 | 121.3500 | 133.5000 | 145.7500 | 159.0000 |
| half heat count | 8.5667 | 3.2662 | 4.0000 | 4.4500 | 8.5000 | 14.5500 | 17.0000 |
| Mill failures | 1.8333 | 0.3790 | 1.0000 | 1.0000 | 2.0000 | 2.0000 | 2.0000 |
| Pump failures | 1.8333 | 0.3790 | 1.0000 | 1.0000 | 2.0000 | 2.0000 | 2.0000 |

All runs have 338 heats, 3,211 t billets, 3,082.56 t bars and 50 t ending stock. Each has one ongoing air-leak episode and one ongoing fouling episode. Mill/pump repair event counts equal their failure counts. Direct per-seed counts and errors are in [seed_results.csv](phase1_audit/seed_results.csv), with each independent constraint check in [seed_checks.json](phase1_audit/seed_checks.json).

Mean IF SEC spans 648.112-652.244 kWh/t and mean daily electricity 106.459-106.991 MWh; all are inside configured mean benchmark envelopes. Frozen seed 42 is about 0.72 SD above the additional-seed MWh mean; it is not an extreme benchmark match. Half-power counts vary 4-17; binomial occurrence variation is not constrained to +/-10% of a nominal rare-fault count. No rates were adjusted to pass.

**W09:** seeds 2, 25 and 27 reach zero interval-end inventory. Many additional runs also have a conservative intraslot lower bound of zero. No negative stock or throughput loss is seen, but disruption slack is small. **W02:** additional runs have 4-15 individual working days above the 107.1 MWh daily benchmark, despite all run means passing. This is not a demand/energy-balance violation.

## UCI versus simulator temporal behaviour

UCI comparison uses independently computed Jan-Aug 2018 statistics from the existing clean 15-minute table. Normalize each sequence by its own mean; no absolute Korean plant power is transplanted. ACF is Pearson correlation across lagged pairs, computed through 192 lags (48 h). Ramps are differences divided by sequence mean. Curves contain every retained slot, including off-days and load tails. No fitting is done and no parameter is changed.

The ramp histogram displays the central -2 to +2 range; 1.226% of UCI ramps and 0.000% of simulator ramps fall outside that display. Full-tail SD/quantiles and min/max are retained in temporal_diagnostics.json. ACF/load-duration calculations use all slots without trimming.

![Normalized profile, ACF, ramp distributions and load-duration curves](phase1_audit/temporal_comparison.png)

| Sequence | Lag 1 (15 min) | Lag 4 (60 min) | Lag 7 (105 min) | Lag 14 (210 min) | Lag 96 (1 day) |
|---|---:|---:|---:|---:|---:|
| UCI Jan-Aug | 0.9094 | 0.6879 | 0.5781 | 0.3735 | 0.6056 |
| Simulator MAIN truth | 0.6659 | 0.1502 | 0.8010 | 0.6953 | 0.3121 |
| Simulator IF truth | 0.6001 | 0.0102 | 0.7945 | 0.6872 | 0.3547 |
| Simulator non-IF truth | 0.9741 | 0.8802 | 0.7848 | 0.5711 | 0.4748 |
| Analytic 78+27 cycle | 0.2865 | -0.3933 | 1.0000 | 1.0000 | -0.3933 |

| Sequence | Normalized ramp SD | P01 | P10 | P25 | P50 | P75 | P90 | P99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| UCI Jan-Aug | 0.5094 | -1.7674 | -0.3638 | -0.0163 | 0.0000 | 0.0163 | 0.4027 | 1.6896 |
| Simulator MAIN truth | 0.5176 | -1.2594 | -0.7614 | -0.0048 | -0.0001 | 0.0089 | 0.7778 | 1.2135 |

| Sequence | Normalized load min | P10 | P50 | P90 | P99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| UCI Jan-Aug | 0.0862 | 0.1001 | 0.1650 | 2.8859 | 4.3291 | 5.3206 |
| Simulator MAIN truth | 0.0241 | 0.0307 | 1.3833 | 1.6159 | 1.6205 | 1.6233 |

### Lag-4 investigation — structural explanation supported

The actual IF cycle averages **105.716073 min**, powered **78.348282 min**, non-powered **27.309025 min**, and outage **0.058767 min** per heat. FFT of existing IF energy has a dominant short-cycle period of **102.857143 min**, close to seven 15-minute slots. ACF peaks at lag 7 and its multiples. Lag 4 is about half a cycle away and crosses charging breaks.

An independent analytic square duty cycle constructed from **6500 kWh/5000 kW = 78 powered min plus 27 non-powered min**, sampled by exact 15-minute integration, has lag-4 ACF **-0.393261** and lag-7 ACF 1. This is not a simulator replay or a tuned fit. The actual random heat lengths and daily/off-day level effects soften that periodic anticorrelation.

The decomposition supports causation: actual IF lag-4 is **0.010200**, while non-IF loads alone are **0.880152**. Removing off-day/inter-day level pairs makes within-working-day MAIN lag-4 **-0.384523**, IF **-0.453341**, versus UCI weekdays **0.638813**. Those within-day selections follow each plant's stated working calendar (simulation Monday-Saturday, UCI weekdays Monday-Friday). Sensor noise is not the cause: observed MAIN lag-4 is 0.144242. The single dominant on/off furnace is the principal source of the mismatch, with scheduled rolling and off-day loads affecting the aggregate value.

![Cycle attribution ACF](phase1_audit/cycle_acf.png)

**W06:** similar ramp SD (about 0.51) does not imply temporal realism equivalence. UCI has strong day shifts and smoother intra-shift loads; the simulator is largely repetitive furnace duty with a 24-hour working calendar, 16-hour mill and Sunday outages. Normalized profile and load-duration shape remain visibly different. This corroborates the existing lag-4 caveat and does not justify recalibration simply to imitate UCI.

## Source/config constant audit

AST inspection collected every numeric literal in the simulator, its validator and schema. Complete locations: [source_numeric_constants.json](phase1_audit/source_numeric_constants.json). Important **physical** sizes/ratings/energy losses/yields/capacity/PF/buffer/temperatures/coal properties/fault rates and gains/sensor rates are read from the versioned configuration in the simulation engine. No hidden 5000 kW or 650 kWh/t plant-sizing literal controls V1 mechanics.

**W07:** remaining literals/limitations:

- `engine.py:42`: signature defaults seed=42, days=30. Config seed is used only when `seed=None`; explicit audited seed arguments match the frozen manifest. A caller editing only config seed and omitting the seed argument would still get 42.
- `engine.py:55`, `:170`, `:178`: 15-minute contract and 96-slot day/indexing remain fixed; `:294` divides hours into hard-coded 8-hour shifts. These agree with the current config but are not independent configurable shift durations.
- `scenario.py:14,37,51` and engine calendar: 1440 min/day, 60 min/h, half-slot midpoint and hour arithmetic are unit/calendar structure, not missing technical values.
- `schema.py:21`: inventory max 200 t is hard-coded in schema construction, rather than read from plant config; it agrees with the snapshot now but could drift in a later plant variant. Percent/PF/unit bounds and one/zero arithmetic are schema mathematics.
- Some 1e-8/1e-10 numerical tolerances are hard-coded outside the configured acceptance tolerance. They agree with or are tighter than current tests; later tolerance changes would not propagate universally.
- `calendar.annual_days`, `if.cycle_min`, `if.baseline_powered_min` and `if.baseline_sec` are descriptive fields, not directly imposed on stochastic V1. V1 heat time actually derives from best SEC + practice + physical faults, power and `nonpowered_min`. The 105-min nominal cycle is not a fixed cycle independent of energy. Do not expect editing the nominal field alone to change operations.
- `engine.py:139` hard-codes `chem_ok=True`. `:237` imposes RHF discharge temperature. These are explicitly disclosed placeholders, but actual chemistry/thermal feasibility is outside demonstrated validation.

## Remaining warnings and interpretation

**W03:** the capacity/stock/rolling-window reconciliation is transparent and feasible, but changing thirteen full heats, output targets and a 16-hour rolling window relative to the approximate PDF is a substantive plant-spec choice. The asset table explains its electrical consequences; it is not an apples-to-apples fixed-output comparison against 102 MWh.

**W04:** calendar wear continues while off and resets after assumed 15-30-minute repairs. Two-week cycles imply far more than 3-4 annual failures if extrapolated. Their slopes and replacements are configured assumptions, not UCI/AI4I/IMS-derived reliability. The baseline meets production because available rolling/furnace time and stock buffer suffice for those particular short repairs. Do not extrapolate field maintenance performance, quality assurance or annual reliability from these outputs.

**W08:** the physical half-power mechanism is consistent and labels eight malfunctioning heats. It is nevertheless lower than full rated power by design. The configured normal-practice check's exclusion of `half` is legitimate for injected baseline faults but cannot be represented as universal full-power compliance; future accepted schedules must distinguish faults from permitted decisions.

## Disposition

Retain the immutable Phase-I artefact as audited evidence. Physical feasibility and reproduction are supported for the frozen run and tested seed sample. **Do not call the public/hidden boundary fully validated or hand the existing features to Phase II as leakage-safe until B01 is resolved or the boundary requirement is explicitly revised.** Warnings do not independently authorize or require unfreezing. No implementation change, dataset change, new parameter value, optimisation, predictive model or savings claim accompanies this report.

Machine-readable evidence: [independent KPI/constraint checks](phase1_audit/frozen_independent_checks.json), [provenance](phase1_audit/provenance.json), [seed distributions](phase1_audit/seed_distribution_summary.json), [temporal diagnostics](phase1_audit/temporal_diagnostics.json), [fault examples](phase1_audit/fault_examples.json), [boundary attack](phase1_audit/boundary_audit.json).
