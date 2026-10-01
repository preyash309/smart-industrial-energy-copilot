# Phase-I assumption register

Read all four supplied PDFs before implementation: Smart_Industrial_Energy_Copilot_Roadmap.pdf, Reference_Plant_Spec_v2.pdf, Data_Workflow (1).pdf and Challenge04_Simple_Workflow.pdf. The current user's Phase-I scope overrides later-stage models/optimisation/savings work in those PDFs. The spec's cited benchmarks are secondary sources; they are not independent measurements at this proposed plant.

## Reconciliation and feasibility

- IF energy: 10 t tapped liquid * 650 kWh/t = 6500 kWh. Rated 5000 kW gives 1.3 h = 78 powered minutes. Approximate 105-minute cycle minus 78 gives 27 minutes charging/tapping/non-powered work. Discard the conflicting ~90-minute power-on approximation. Changes in energy change powered duration through energy/power; non-powered time stays independent. Partial half-power malfunction lasts an assumed 20 powered minutes, adding 10 minutes versus delivering that portion at rated power, plus its specified heat loss. Fault periods are explicit exceptions to ordinary full-power operation.
- Ten tonnes denotes crucible/tapped liquid, not gross charge: assumed 98% melt yield gives 10/0.98 = 10.2041 t charge; 0.2041 t melt loss. Liquid-to-billet yield is 95%, rolling yield 96%; losses are explicit mass sinks.
- Thirteen 10 t heats give 130 t liquid, 123.5 t billets and 118.56 t bars. These are close to, but above, the spec's approximate 125/120/115 figures. They avoid an impossible half heat while retaining 12-13 heats/day. Baseline nominal IF energy is 84.5 MWh/working day versus approximate 81.3 in the spec.
- Fifteen hours at 8 t/h handles only 120 t billets. Use a disclosed 16 h rolling window, capacity 128 t, to meet 123.5 t plus short repair interruptions. Fifty tonnes of opening stock bridges the timing mismatch before late furnace taps. The initial 30 t trial failed throughput; stopped and corrected before extending the run. Maximum yard remains 200 t.
- RHF blower/pusher power is missing from the spec's daily electricity breakdown. Explicitly add an assumed 40 kW during the rolling window rather than silently omit feeder M4. MAIN is not a seventh consuming asset; it aggregates six consuming branches. Caster mechanics belong to AUX electricity and a separate mass-transfer stage.
- Electrical PF uses compensated per-feeder assumptions, not the very different UCI whole-plant PF. Sum complex powers for MAIN kVA and test full-power subslot concurrency against 7000 kVA; do not divide all loads by an invented universal PF.
- Quick 15-30-minute replacement of worn parts is assumed with spare parts. Wear ramps over about two weeks, giving accelerated failure cycles in the demonstration, not 3-4 annual failures. Repair assumptions materially limit production conclusions.

## Evidence and data boundaries

The UCI midnight-row convention is inferred from every day's source order; retain original timestamps and use corrected interval starts. Calibration only uses Jan-Aug. Full-year EDA includes held-out descriptive observations and does not fit parameters. UCI dimensions transfer normalized rhythm to AUX only; absolute consumption and public PF do not set reference plant size. Process fluctuations do not identify meter accuracy. AI4I is synthetic and never row-merged with plant data.

Punjab is the selected tariff jurisdiction and kVAh the billing basis. The current official FY2026-27 tariff was inspected at https://docs.pspcl.in/docs/cecommercial2620260310162642809.pdf ; the supplied workflow's seasonal peak/night clock bands are used for an energy view only. No billing rate, fuel price, emissions total, payback or savings claim is implemented; applicable rates/customer class need a later explicit pricing stage.

Detailed chemistry, measured pump curves, RHF transient coefficients, holidays and real ambient data are absent. They remain disclosed reduced-order assumptions or unimplemented details. No latent health/fault severity/future failure timestamps may become downstream features.

## Complete plant parameter register

| Parameter | Value | Unit | Status | Source | Notes |
|---|---|---|---|---|---|
| seed | 42 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | One global seed; stable independent Generator streams. |
| clock_minutes | 15 | min | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Shared interval; subslot overlap integration preserves physical heat times. |
| calendar.off_weekdays | [6] | weekday index | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Sunday off; Monday index zero; no invented holiday calendar. |
| calendar.annual_days | 300 | working day/year | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Planning reference, not imposed on a 30-day calendar. |
| calendar.heats_per_day | 13 | heat/working day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Upper end of 12-13; 130 t liquid -> 123.5 t billet -> 118.56 t bar. |
| calendar.mill_start_hour | 0 | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Continuous rolling shift starts at midnight; initial stock bridges first heat. |
| calendar.mill_hours | 16 | h/working day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 15 h cannot consume 123.5 t at 8 t/h; 16 h accommodates fault interruptions. |
| if.liquid_per_heat | 10 | t | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 10 t denotes tapped liquid/crucible capacity; charge includes melt loss. |
| if.melt_yield | 0.98 | t liquid/t charge | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Not specified; explicit placeholder requiring pilot confirmation. |
| if.rated_kw | 5000 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Full power during normal melting; anomalous half-power fault explicitly recorded. |
| if.best_sec | 570 | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 10 (secondary citation; not field verification) | Otto Junker foundry best practice; transfer to billet shop unverified. |
| if.practice_loss | 60 | kWh/t liquid | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Chronic operator practice losses from spec Section 12. |
| if.baseline_fault_loss | 20 | kWh/t liquid | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | V0 effective fault allowance; V1 replaces with physical fault contributions. |
| if.baseline_sec | 650 | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 10 (secondary citation; not field verification) | Representative point in cluster range, not measured plant baseline. |
| if.baseline_powered_min | 78 | min | derived | Readme/Reference_Plant_Spec_v2.pdf, Sections 4,5,10; explicit calculation | 10*650/5000*60 = 78, replacing inconsistent ~90-min power-on. |
| if.cycle_min | 105 | min | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Approximate baseline tap-to-tap target. |
| if.nonpowered_min | 27 | min | derived | Readme/Reference_Plant_Spec_v2.pdf, Sections 4,5,10; explicit calculation | 105 - 78 = 27 charging/tapping/non-powered minutes. |
| if.tap_temp | 1640 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Spec target; detailed chemistry out of scope. |
| if.tap_min | 1620 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Quality window missing in spec: engineering assumption to confirm. |
| if.tap_max | 1710 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Allows specified +50 K superheat while labelling waste; metallurgy to confirm. |
| if.pf | 0.97 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Compensated induction panel; UCI whole-site PF cannot be transplanted. |
| material.cast_yield | 0.95 | t billet/t liquid | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Caster instantaneous at tap; delay not sourced. |
| material.rolling_yield | 0.96 | t bar/t billet | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Scale/crop losses; explicit mass sinks. |
| material.initial_yard | 50 | t | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 16 h rolling consumes 123.5 t before last heats tap; opening buffer must bridge roughly 38 t timing deficit. |
| material.yard_min | 0 | t | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Hard lower bound. |
| material.yard_max | 200 | t | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Hard upper bound. |
| material.billet_target | 123.5 | t/working day | derived | Readme/Reference_Plant_Spec_v2.pdf, Sections 4,5,10; explicit calculation | 13*10*0.95; spec approximate 120. |
| material.bar_target | 118.56 | t/working day | derived | Readme/Reference_Plant_Spec_v2.pdf, Sections 4,5,10; explicit calculation | 123.5*0.96; spec approximate 115. |
| mill.capacity_tph | 8 | t billet/h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Matched RHF throughput. |
| mill.rating_kw | 1200 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Main drive nameplate. |
| mill.sec | 100 | kWh/t bar | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 10 (secondary citation; not field verification) | Approximate bar-mill SEC; power follows tonnes, below nameplate. |
| mill.pf | 0.95 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Compensated motor; assumption. |
| mill.base_temp | 55 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Healthy bearing baseline; no measured source. |
| mill.base_vibration | 1.5 | mm/s | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Healthy RMS vibration; no measured source. |
| mill.rpm | 1500 | rpm | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Nominal speed placeholder. |
| rhf.capacity_tph | 8 | t billet/h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Pusher capacity. |
| rhf.temp | 1200 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Midpoint of discharge limits. |
| rhf.temp_min | 1150 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Hard discharge bound. |
| rhf.temp_max | 1250 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Hard discharge bound. |
| rhf.fuel_sec | 1.48 | GJ/t bar | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 10 (secondary citation; not field verification) | TERI 2015 cluster mean; not a thermal first-principles model. |
| rhf.coal_ncv | 22 | GJ/t coal | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Confirm purchased fuel analysis. |
| rhf.electric_kw | 40 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Blower/pusher missing from daily electricity table; explicit added load. |
| rhf.hold_fuel | 20 | kg/h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Holding coal during mill repair, no output; unsourced placeholder. |
| rhf.pf | 0.95 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Motor compensation assumption. |
| rhf.flue_temp | 350 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Baseline exhaust; unsourced placeholder. |
| pump.rating_kw | 75 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Continuous circulation baseline gives 1.8 MWh/day. |
| pump.pf | 0.96 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Motor compensation assumption. |
| pump.flow | 100 | m3/h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Not specified; confirm engineering data. |
| pump.min_flow | 80 | m3/h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | IF permissive threshold, provisional safety setting. |
| pump.base_vibration | 1 | mm/s | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Healthy baseline assumption. |
| pump.base_temp | 40 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Healthy bearing assumption. |
| compressor.rating_kw | 90 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Nameplate. |
| compressor.loaded_kw | 85 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Operating duty below nameplate. |
| compressor.idle_kw | 42.5 | kW | derived | Readme/Reference_Plant_Spec_v2.pdf, Sections 4,5,10; explicit calculation | (1700 - 16*85)/8; baseline ~1.7 MWh/working day. |
| compressor.pf | 0.95 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Motor compensation assumption. |
| compressor.pressure | 7 | bar | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Not specified; placeholder. |
| aux.average_kw | 250 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 6 MWh/day includes caster/cranes/fume; six electrical branches incl. RHF. |
| aux.pf | 0.96 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Compensated composite load. |
| aux.profile_blend | 0.15 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 15% UCI training profile shape, 85% flat; transfer rhythm conservatively. |
| aux.offday_fraction | 0.35 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Sunday background fraction, not copied absolute UCI size. |
| faults.superheat_probability | 0.2 | probability/heat | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Rate is assumed, not measured. |
| faults.superheat_k | 50 | K | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Plant-spec mechanism. |
| faults.superheat_loss | 20 | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 12 (secondary citation; not field verification) | Otto Junker loss table via spec Section 12. |
| faults.lid_probability | 0.3 | probability/heat | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed occurrence rate. |
| faults.lid_minutes | 20 | min | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Specified open duration. |
| faults.lid_loss | 15 | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 12 (secondary citation; not field verification) | Heat loss from lid exposure. |
| faults.charge_probability | 0.4 | probability/heat | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed rusty/loose-charge fraction. |
| faults.charge_loss | [25, 30] | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 12 (secondary citation; not field verification) | Spec loss range. |
| faults.half_probability | 0.025 | probability/heat | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Rare fault; violates normal full-power practice and is flagged. |
| faults.half_fraction | 0.5 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Specified half-power malfunction. |
| faults.half_minutes | 20 | min | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed partial-heat fault duration; remainder recovers rated power. |
| faults.half_loss | 20 | kWh/t liquid | sourced | Readme/Reference_Plant_Spec_v2.pdf, Section 12 (secondary citation; not field verification) | Longer exposure loss. |
| faults.practice_sd | 3 | kWh/t liquid | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Physical practice variation, not meter noise. |
| faults.delay_probability | 0.12 | probability/heat | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Charge/tap delay assumption. |
| faults.delay_max | 4 | min | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Small non-powered delay; capacity slack. |
| faults.leak_onset_day | 8 | day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed calendar onset; fixed before decisions. |
| faults.leak_extra_kw | 15 | kW | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Idle wasted compressor power; capped at nameplate. |
| faults.fouling_daily | 0.003 | severity/day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Calendar deposit accumulation; fuel and flue effects. |
| faults.fouling_loss | 0.05 | fraction at full severity | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Spec approximately 5% additional coal. |
| faults.fouling_flue | 40 | K at full severity | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Flue response magnitude assumed. |
| faults.wear_days | [13, 16] | day to threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Spec roughly two weeks; calendar-age hazard, no NASA data used. |
| faults.repair_hours | [0.25, 0.5] | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed quick bearing/impeller replacement with spares; validate locally. |
| faults.mill_vibration_gain | 5 | mm/s at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Monotone wear response assumption. |
| faults.mill_temp_gain | 25 | K at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Monotone wear response assumption. |
| faults.mill_energy_gain | 0.02 | fraction at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Friction increases drive energy. |
| faults.pump_flow_loss | 0.15 | fraction at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Impeller erosion reduces flow. |
| faults.pump_vibration_gain | 4 | mm/s at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Wear/cavitation response assumption. |
| faults.pump_temp_gain | 15 | K at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Wear response assumption. |
| faults.pump_efficiency_loss | 0.05 | fraction at wear threshold | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Reduced hydraulic efficiency; nameplate cap enforced. |
| faults.initial_wear | 0.02 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Newly maintained baseline. |
| observations.relative_noise | 0.005 | standard deviation/value | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Engineering meter error; process CV is not meter error. |
| observations.missing_probability | 0.005 | probability/channel/slot | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Readme/Data_Workflow (1).pdf D5 stress-test rate; UCI has no missing observations. |
| observations.glitch_probability | 0.0005 | probability/channel/slot | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Assumed rare multiplicative spikes. |
| observations.glitch_multiplier | 3 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Observation only; never alters physical ledger. |
| observations.sensor_noise | 0.005 | relative standard deviation | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Sensor channels independent from meter channels. |
| weather.mean | 25 | degC | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Synthetic ambient; no real weather feed. |
| weather.daily_amplitude | 5 | K | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Diurnal ambient assumption. |
| weather.sd | 1 | K | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Exogenous variation; influences bearing temperatures. |
| tariff.peak_start | 18 | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Evening ToD band from Data Workflow D1. |
| tariff.peak_end | 22 | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Evening ToD band. |
| tariff.night_start | 22 | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Night band. |
| tariff.night_end | 6 | h | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Night band. |
| acceptance.contract_kva | 7000 | kVA | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Hard contract demand bound, also checked at subslot concurrency. |
| acceptance.sec_range | [640, 660] | kWh/t liquid | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Required mean baseline envelope. |
| acceptance.daily_mwh | [96.9, 107.1] | MWh/working day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 102 +/-5%; off-days reported separately. |
| acceptance.if_share | [0.75, 0.85] | fraction | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Working-day electricity share. |
| acceptance.coal_tpd | [7, 9] | t/working day | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | 7.7 t reference adjusted to 118.56 t bars/day; holding and fouling included. |
| acceptance.tolerance | 1e-08 | t or kWh | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Floating-point ledger tolerance. |
| acceptance.acf_absolute | 0.25 | dimensionless | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Cross-plant absolute envelope; not parameter fitting. |
| acceptance.profile_rmse | 1.0 | normalized load | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Wide cross-process envelope declared before comparison. |
| acceptance.ramp_ratio | [0.2, 3.0] | ratio to UCI ramp SD | assumption | Readme/Reference_Plant_Spec_v2.pdf, Sections 4-6,12; Phase-I engineering assumption | Cross-process ramp envelope; discrepancies documented. |
