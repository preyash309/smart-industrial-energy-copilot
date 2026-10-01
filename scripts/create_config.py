"""Transcribe the supplied spec; label unsourced engineering choices explicitly."""
from pathlib import Path
import yaml
from energy_copilot.common import ROOT, parameter as p, validate_parameters

SPEC = "Readme/Reference_Plant_Spec_v2.pdf"
WORKFLOW = "Readme/Data_Workflow (1).pdf"


def create():
    def a(v, u, note, section="Sections 4-6,12"):
        return p(v, u, "assumption", f"{SPEC}, {section}; Phase-I engineering assumption", note)

    def s(v, u, note, section="Section 10"):
        return p(v, u, "sourced", f"{SPEC}, {section} (secondary citation; not field verification)", note)

    def d(v, u, note):
        return p(v, u, "derived", f"{SPEC}, Sections 4,5,10; explicit calculation", note)

    c = dict(version="plant_v1.1", plant_id="SE_REFERENCE_01", start="2026-01-05T00:00:00",
             timezone="Asia/Kolkata", seed=a(42,"dimensionless","One global seed; stable independent Generator streams."),
             clock_minutes=a(15,"min","Shared interval; subslot overlap integration preserves physical heat times."),
             stochastic=True, calibration_file="configs/calibration_v1.yaml")
    c["calendar"] = dict(off_weekdays=a([6],"weekday index","Sunday off; Monday index zero; no invented holiday calendar."),
                         maintenance_dates=[], annual_days=a(300,"working day/year","Planning reference, not imposed on a 30-day calendar."),
                         heats_per_day=a(13,"heat/working day","Upper end of 12-13; 130 t liquid -> 123.5 t billet -> 118.56 t bar."),
                         mill_start_hour=a(0,"h","Continuous rolling shift starts at midnight; initial stock bridges first heat."),
                         mill_hours=a(16,"h/working day","15 h cannot consume 123.5 t at 8 t/h; 16 h accommodates fault interruptions."))
    c["if"] = dict(liquid_per_heat=a(10,"t","10 t denotes tapped liquid/crucible capacity; charge includes melt loss."),
                    melt_yield=a(0.98,"t liquid/t charge","Not specified; explicit placeholder requiring pilot confirmation."),
                    rated_kw=a(5000,"kW","Full power during normal melting; anomalous half-power fault explicitly recorded."),
                    best_sec=s(570,"kWh/t liquid","Otto Junker foundry best practice; transfer to billet shop unverified."),
                    practice_loss=a(60,"kWh/t liquid","Chronic operator practice losses from spec Section 12."),
                    baseline_fault_loss=a(20,"kWh/t liquid","V0 effective fault allowance; V1 replaces with physical fault contributions."),
                    baseline_sec=s(650,"kWh/t liquid","Representative point in cluster range, not measured plant baseline."),
                    baseline_powered_min=d(78,"min","10*650/5000*60 = 78, replacing inconsistent ~90-min power-on."),
                    cycle_min=a(105,"min","Approximate baseline tap-to-tap target."),
                    nonpowered_min=d(27,"min","105 - 78 = 27 charging/tapping/non-powered minutes."),
                    tap_temp=a(1640,"degC","Spec target; detailed chemistry out of scope."),
                    tap_min=a(1620,"degC","Quality window missing in spec: engineering assumption to confirm."),
                    tap_max=a(1710,"degC","Allows specified +50 K superheat while labelling waste; metallurgy to confirm."),
                    pf=a(0.97,"dimensionless","Compensated induction panel; UCI whole-site PF cannot be transplanted."))
    c["material"] = dict(cast_yield=a(0.95,"t billet/t liquid","Caster instantaneous at tap; delay not sourced."),
                         rolling_yield=a(0.96,"t bar/t billet","Scale/crop losses; explicit mass sinks."),
                         initial_yard=a(50,"t","16 h rolling consumes 123.5 t before last heats tap; opening buffer must bridge roughly 38 t timing deficit."),
                         yard_min=a(0,"t","Hard lower bound."), yard_max=a(200,"t","Hard upper bound."),
                         billet_target=d(123.5,"t/working day","13*10*0.95; spec approximate 120."),
                         bar_target=d(118.56,"t/working day","123.5*0.96; spec approximate 115."))
    c["mill"] = dict(capacity_tph=a(8,"t billet/h","Matched RHF throughput."), rating_kw=a(1200,"kW","Main drive nameplate."),
                      sec=s(100,"kWh/t bar","Approximate bar-mill SEC; power follows tonnes, below nameplate."),
                      pf=a(0.95,"dimensionless","Compensated motor; assumption."),
                      base_temp=a(55,"degC","Healthy bearing baseline; no measured source."),
                      base_vibration=a(1.5,"mm/s","Healthy RMS vibration; no measured source."),
                      rpm=a(1500,"rpm","Nominal speed placeholder."))
    c["rhf"] = dict(capacity_tph=a(8,"t billet/h","Pusher capacity."), temp=a(1200,"degC","Midpoint of discharge limits."),
                     temp_min=a(1150,"degC","Hard discharge bound."),temp_max=a(1250,"degC","Hard discharge bound."),
                     fuel_sec=s(1.48,"GJ/t bar","TERI 2015 cluster mean; not a thermal first-principles model."),
                     coal_ncv=a(22,"GJ/t coal","Confirm purchased fuel analysis."),
                     electric_kw=a(40,"kW","Blower/pusher missing from daily electricity table; explicit added load."),
                     hold_fuel=a(20,"kg/h","Holding coal during mill repair, no output; unsourced placeholder."),
                     pf=a(0.95,"dimensionless","Motor compensation assumption."),
                     flue_temp=a(350,"degC","Baseline exhaust; unsourced placeholder."))
    c["pump"] = dict(rating_kw=a(75,"kW","Continuous circulation baseline gives 1.8 MWh/day."),
                      pf=a(0.96,"dimensionless","Motor compensation assumption."),flow=a(100,"m3/h","Not specified; confirm engineering data."),
                      min_flow=a(80,"m3/h","IF permissive threshold, provisional safety setting."),
                      base_vibration=a(1,"mm/s","Healthy baseline assumption."),base_temp=a(40,"degC","Healthy bearing assumption."))
    c["compressor"] = dict(rating_kw=a(90,"kW","Nameplate."),loaded_kw=a(85,"kW","Operating duty below nameplate."),
                            idle_kw=d(42.5,"kW","(1700 - 16*85)/8; baseline ~1.7 MWh/working day."),
                            pf=a(0.95,"dimensionless","Motor compensation assumption."), pressure=a(7,"bar","Not specified; placeholder."))
    c["aux"] = dict(average_kw=a(250,"kW","6 MWh/day includes caster/cranes/fume; six electrical branches incl. RHF."),
                     pf=a(0.96,"dimensionless","Compensated composite load."),
                     profile_blend=a(0.15,"dimensionless","15% UCI training profile shape, 85% flat; transfer rhythm conservatively."),
                     offday_fraction=a(0.35,"dimensionless","Sunday background fraction, not copied absolute UCI size."))
    c["faults"] = dict(
        superheat_probability=a(0.20,"probability/heat","Rate is assumed, not measured."), superheat_k=a(50,"K","Plant-spec mechanism."),
        superheat_loss=s(20,"kWh/t liquid","Otto Junker loss table via spec Section 12.","Section 12"),
        lid_probability=a(0.30,"probability/heat","Assumed occurrence rate."), lid_minutes=a(20,"min","Specified open duration."),
        lid_loss=s(15,"kWh/t liquid","Heat loss from lid exposure.","Section 12"),
        charge_probability=a(0.40,"probability/heat","Assumed rusty/loose-charge fraction."), charge_loss=s([25,30],"kWh/t liquid","Spec loss range.","Section 12"),
        half_probability=a(0.025,"probability/heat","Rare fault; violates normal full-power practice and is flagged."),
        half_fraction=a(0.5,"dimensionless","Specified half-power malfunction."), half_minutes=a(20,"min","Assumed partial-heat fault duration; remainder recovers rated power."), half_loss=s(20,"kWh/t liquid","Longer exposure loss.","Section 12"),
        practice_sd=a(3,"kWh/t liquid","Physical practice variation, not meter noise."),
        delay_probability=a(0.12,"probability/heat","Charge/tap delay assumption."), delay_max=a(4,"min","Small non-powered delay; capacity slack."),
        leak_onset_day=a(8,"day","Assumed calendar onset; fixed before decisions."),leak_extra_kw=a(15,"kW","Idle wasted compressor power; capped at nameplate."),
        fouling_daily=a(0.003,"severity/day","Calendar deposit accumulation; fuel and flue effects."),
        fouling_loss=a(0.05,"fraction at full severity","Spec approximately 5% additional coal."),
        fouling_flue=a(40,"K at full severity","Flue response magnitude assumed."),
        wear_days=a([13,16],"day to threshold","Spec roughly two weeks; calendar-age hazard, no NASA data used."),
        repair_hours=a([0.25,0.5],"h","Assumed quick bearing/impeller replacement with spares; validate locally."),
        mill_vibration_gain=a(5,"mm/s at wear threshold","Monotone wear response assumption."),
        mill_temp_gain=a(25,"K at wear threshold","Monotone wear response assumption."),
        mill_energy_gain=a(0.02,"fraction at wear threshold","Friction increases drive energy."),
        pump_flow_loss=a(0.15,"fraction at wear threshold","Impeller erosion reduces flow."),
        pump_vibration_gain=a(4,"mm/s at wear threshold","Wear/cavitation response assumption."),
        pump_temp_gain=a(15,"K at wear threshold","Wear response assumption."),
        pump_efficiency_loss=a(0.05,"fraction at wear threshold","Reduced hydraulic efficiency; nameplate cap enforced."),
        initial_wear=a(0.02,"dimensionless","Newly maintained baseline."))
    c["observations"] = dict(relative_noise=a(0.005,"standard deviation/value","Engineering meter error; process CV is not meter error."),
                             missing_probability=a(0.005,"probability/channel/slot",f"{WORKFLOW} D5 stress-test rate; UCI has no missing observations."),
                             glitch_probability=a(0.0005,"probability/channel/slot","Assumed rare multiplicative spikes."),
                             glitch_multiplier=a(3,"dimensionless","Observation only; never alters physical ledger."),
                             sensor_noise=a(0.005,"relative standard deviation","Sensor channels independent from meter channels."))
    c["weather"] = dict(mean=a(25,"degC","Synthetic ambient; no real weather feed."),daily_amplitude=a(5,"K","Diurnal ambient assumption."),
                         sd=a(1,"K","Exogenous variation; influences bearing temperatures."))
    c["tariff"] = dict(jurisdiction="Punjab", basis="kVAh", mode="bands_only_no_billing", 
                       source="https://docs.pspcl.in/docs/cecommercial2620260310162642809.pdf",
                       notes="FY2026-27 official tariff checked. Bands retained for descriptive energy view; no rate, bill or savings claims.",
                       peak_start=a(18,"h","Evening ToD band from Data Workflow D1."),peak_end=a(22,"h","Evening ToD band."),
                       night_start=a(22,"h","Night band."),night_end=a(6,"h","Night band."),
                       peak_season_start="06-16",peak_season_end="10-15")
    c["acceptance"] = dict(contract_kva=a(7000,"kVA","Hard contract demand bound, also checked at subslot concurrency."),
                            sec_range=a([640,660],"kWh/t liquid","Required mean baseline envelope."),
                            daily_mwh=a([96.9,107.1],"MWh/working day","102 +/-5%; off-days reported separately."),
                            if_share=a([0.75,0.85],"fraction","Working-day electricity share."),
                            coal_tpd=a([7,9],"t/working day","7.7 t reference adjusted to 118.56 t bars/day; holding and fouling included."),
                            tolerance=a(1e-8,"t or kWh","Floating-point ledger tolerance."),
                            acf_absolute=a(0.25,"dimensionless","Cross-plant absolute envelope; not parameter fitting."),
                            profile_rmse=a(1.0,"normalized load","Wide cross-process envelope declared before comparison."),
                            ramp_ratio=a([0.2,3.0],"ratio to UCI ramp SD","Cross-process ramp envelope; discrepancies documented."))
    validate_parameters(c)
    out = ROOT / "configs/plant_v1.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(c, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    create()
