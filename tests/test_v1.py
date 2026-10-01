import copy
import numpy as np
import pandas as pd
import pytest
from energy_copilot.common import load_config
from energy_copilot.sim import simulate


@pytest.fixture(scope="module")
def v1():
    return simulate(days=2)


def test_stochastic_48h_gate(v1):
    assert all(v1.summary["checks"].values())
    assert 640<=v1.summary["mean_if_sec_kWh_t"]<=660


def test_noise_missingness_glitches_never_change_physical_state(v1):
    c=load_config()
    for name in ("relative_noise","sensor_noise","missing_probability","glitch_probability"):
        c["observations"][name]["value"]=0
    noiseless=simulate(c,days=2)
    pd.testing.assert_frame_equal(v1.latent_truth,noiseless.latent_truth,check_exact=True)
    pd.testing.assert_frame_equal(v1.latent_heats,noiseless.latent_heats,check_exact=True)
    assert v1.scenario_manifest["scenario_sha256"]==noiseless.scenario_manifest["scenario_sha256"]
    assert v1.readings.kWh.isna().any()
    assert v1.readings.sensor_glitch.any()


def test_scenario_replays_before_schedule_practice(v1):
    replay=simulate(practice={"practice_loss":45,"suppress_lid":True},days=2)
    assert v1.scenario_manifest["scenario_sha256"]==replay.scenario_manifest["scenario_sha256"]
    pd.testing.assert_series_equal(v1.latent_truth.ambient_C,replay.latent_truth.ambient_C,check_exact=True)
    pd.testing.assert_series_equal(v1.latent_truth.latent_wear,replay.latent_truth.latent_wear,check_exact=True)
    schedule={row.heat_id:row.start for row in v1.latent_heats.itertuples()}
    scheduled=simulate(schedule=schedule,days=2)
    pd.testing.assert_frame_equal(v1.latent_truth,scheduled.latent_truth,check_exact=True)
    assert scheduled.scenario_manifest["scenario_sha256"]==v1.scenario_manifest["scenario_sha256"]


def diagnostic_config():
    c=load_config()
    # Low-throughput mechanism experiment is explicitly not the baseline acceptance case.
    c["calendar"]["heats_per_day"]["value"]=8
    c["material"]["billet_target"]["value"]=76
    c["material"]["bar_target"]["value"]=72.96
    for key in ("superheat_probability","lid_probability","charge_probability","half_probability","delay_probability","practice_sd"):
        c["faults"][key]["value"]=0
    return c


@pytest.mark.parametrize("fault,flag",[("superheat","superheat"),("lid","lid"),("charge","charge_bad"),("half","half")])
def test_if_faults_are_energy_temperature_duration_mechanisms(fault,flag):
    c=diagnostic_config()
    plain=simulate(c,practice={"practice_loss":60},days=1)
    c["faults"][fault+"_probability"]["value"]=1
    bad=simulate(c,practice={"practice_loss":60},days=1)
    assert bad.latent_heats.fault_label.str.contains(flag).all()
    assert (bad.latent_heats.kWh>plain.latent_heats.kWh).all()
    assert (bad.latent_heats.powered_min>plain.latent_heats.powered_min).all()
    if fault=="superheat":
        assert np.allclose(bad.latent_heats.tap_temp_C-plain.latent_heats.tap_temp_C,50)
    if fault=="half":
        assert bad.latent_heats.powered_min.iloc[0]==pytest.approx(bad.latent_heats.kWh.iloc[0]/5000*60+10)


def test_fouling_and_leak_affect_fuel_exhaust_idle_power():
    c=diagnostic_config();c["faults"]["leak_onset_day"]["value"]=0
    bad=simulate(c,practice={"practice_loss":60},days=1)
    c["faults"]["fouling_daily"]["value"]=0;c["faults"]["leak_extra_kw"]["value"]=0
    plain=simulate(c,practice={"practice_loss":60},days=1)
    b=bad.latent_truth;p=plain.latent_truth
    assert b[b.asset_id.eq("RHF_01")].fuel_kg.sum()>p[p.asset_id.eq("RHF_01")].fuel_kg.sum()
    assert b[b.asset_id.eq("RHF_01")].flue_temp_C.max()>p[p.asset_id.eq("RHF_01")].flue_temp_C.max()
    idle=b.asset_id.eq("CMP_01") & b.timestamp.dt.hour.ge(16)
    assert (b.loc[idle,"kW"]>p.loc[idle,"kW"]).all()


def test_v1_same_seed_numeric_identity(v1):
    again=simulate(days=2)
    for name in ("readings","heats","production","events","latent_truth","latent_heats"):
        pd.testing.assert_frame_equal(getattr(v1,name),getattr(again,name),check_exact=True)
    assert v1.scenario_manifest==again.scenario_manifest
