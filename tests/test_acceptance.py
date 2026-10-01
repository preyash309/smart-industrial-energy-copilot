"""30-day acceptance, run only after data, V0 and V1 short-run gates."""
import copy
import numpy as np
import pandas as pd
import pytest
from energy_copilot.common import load_config, values
from energy_copilot.sim import simulate
from energy_copilot.sim.scenario import powered_segments, overlap
from energy_copilot.schema import create_schema, validate_table
from scripts.report import compare_temporal, TEMPORAL_NOTE


@pytest.fixture(scope="module")
def baseline():
    return simulate(days=30)


def test_30_day_baseline_hard_gates(baseline):
    s=baseline.summary
    assert all(s["checks"].values())
    assert s["days"]==30 and s["working_days"]==26
    assert 640<=s["mean_if_sec_kWh_t"]<=660
    assert 12<=s["heats_per_working_day"]<=13
    assert 96.9<=s["mean_working_day_MWh"]<=107.1
    assert .75<=s["if_working_day_share"]<=.85
    assert 7<=s["mean_coal_t_working_day"]<=9
    assert 0<=s["min_yard_t"]<=s["max_yard_t"]<=200
    assert s["peak_kVA"]<=7000


def test_binomial_counts_finite_sample_envelope(baseline):
    c=values(baseline.config);h=baseline.latent_heats
    for name,field in [("superheat","superheat_probability"),("lid","lid_probability"),("charge_bad","charge_probability"),("half","half_probability")]:
        n=len(h);p=c["faults"][field];actual=h.fault_label.str.contains(name).sum()
        assert abs(actual-n*p)<=3*np.sqrt(n*p*(1-p))+1


def test_wear_causes_signals_failure_repairs_and_resets(baseline):
    t=baseline.latent_truth;e=baseline.events
    for asset in ("MILL_01","PMP_01"):
        state=t[t.asset_id.eq(asset)]
        assert state.latent_wear.max()>.95
        assert (state.latent_wear.diff()<-.5).any()
        assert (e.asset_id.eq(asset)&e.type.eq("failure")).any()
        assert (e.asset_id.eq(asset)&e.type.eq("repair")).any()
        assert state.vibration_mm_s.corr(state.latent_wear)>.99
        assert state.temp_C.corr(state.latent_wear)>.7
    pump=t[t.asset_id.eq("PMP_01") & t.working_day & t.pump_available_min.eq(15)]
    assert pump.flow_m3_h.corr(pump.latent_wear)<-.99
    mill=t[t.asset_id.eq("MILL_01") & t.kW.gt(0)]
    assert mill.vibration_mm_s.max()>5


def test_rhf_hold_energy_during_forced_mill_repair():
    c=load_config()
    c["faults"]["wear_days"]["value"]=[.34,.35]  # Exercise an outage during the rolling shift.
    result=simulate(c,practice={"practice_loss":60},days=1)
    rhf=result.latent_truth[result.latent_truth.asset_id.eq("RHF_01")]
    assert rhf.fuel_holding_GJ.sum()>0
    assert all(result.summary["checks"].values())


def test_powered_segments_pause_without_energy_creation():
    parts,end=powered_segments(0,6500,5000,[(30,45)])
    assert end==pytest.approx(93)
    assert sum((b-a)*p/60 for a,b,p in parts)==pytest.approx(6500)
    assert all(overlap(a,b,30,45)==0 for a,b,p in parts)


def test_30_day_reproducibility_numeric_and_file_hash(baseline):
    from energy_copilot.common import sha256, ROOT
    tmp_path=ROOT / "data/runs/test_replay"
    again=simulate(days=30)
    baseline.write(tmp_path / "first");again.write(tmp_path / "second")
    for name in ("readings","heats","production","events","latent_truth","latent_heats"):
        pd.testing.assert_frame_equal(getattr(baseline,name),getattr(again,name),check_exact=True)
        assert sha256(tmp_path / "first" / f"{name}.parquet")==sha256(tmp_path / "second" / f"{name}.parquet")


def test_schema_contracts_and_latent_feature_boundary(baseline):
    schema=create_schema()
    for table in schema["tables"]:
        assert validate_table(getattr(baseline,table),table,schema)
    assert not set(schema["forbidden_features"])&set(schema["readings_features"])
    assert schema["tables"]["latent_truth"]["access"]=="internal_only"


def test_temporal_envelopes_and_discrepancy_are_explicit(baseline):
    comparison=compare_temporal(baseline)
    assert comparison["diagnostics"]["profile_rmse"]["in_envelope"]
    assert comparison["diagnostics"]["ramp_sd_ratio"]["in_envelope"]
    assert comparison["diagnostics"]["lag_1_difference"]["in_envelope"]
    if not comparison["diagnostics"]["lag_4_difference"]["in_envelope"]:
        assert "outside" in TEMPORAL_NOTE and "charging breaks" in TEMPORAL_NOTE
    assert "No post-hoc parameter fitting" in comparison["decision"]
