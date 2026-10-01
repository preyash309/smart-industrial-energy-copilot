"""First gate: exactly 48 deterministic hours. Failures prevent V1 execution."""
import copy
import numpy as np
import pandas as pd
import pytest
from energy_copilot.common import load_config
from energy_copilot.sim import simulate
from energy_copilot.sim.engine import InvariantError
from energy_copilot.sim.validate import validate_simulation


@pytest.fixture(scope="module")
def config():
    c=load_config();c["stochastic"]=False
    c["observations"]["relative_noise"]["value"]=0
    c["observations"]["sensor_noise"]["value"]=0
    return c


@pytest.fixture(scope="module")
def v0(config):
    return simulate(config,seed=42,days=2)


def test_48h_mass_energy_inventory_interlocks(v0):
    assert v0.summary["days"]==2
    assert len(v0.latent_truth)==192*7
    assert all(v0.summary["checks"].values())
    assert v0.summary["heats"]==26
    assert v0.summary["mean_billet_t_working_day"]==pytest.approx(123.5)
    assert v0.summary["mean_bar_t_working_day"]==pytest.approx(118.56)
    assert v0.summary["mean_if_sec_kWh_t"]==pytest.approx(650)


def test_cycle_78_powered_27_nonpowered(v0):
    assert np.allclose(v0.latent_heats.powered_min,78)
    assert np.allclose(v0.latent_heats.nonpowered_min,27)
    assert np.allclose((v0.latent_heats.end-v0.latent_heats.start).dt.total_seconds()/60,105)


def test_exact_fractional_slot_integration(v0):
    feeder=v0.latent_truth[v0.latent_truth.asset_id.eq("IF_01")]
    assert feeder.kWh.sum()==pytest.approx(26*6500)
    assert ((feeder.kW>0)&(feeder.kW<5000)).any()
    assert v0.summary["peak_kVA"]<=7000


def test_reproducibility(v0,config):
    again=simulate(config,seed=42,days=2)
    for name in ("readings","heats","production","events","latent_truth","latent_heats"):
        pd.testing.assert_frame_equal(getattr(v0,name),getattr(again,name),check_exact=True)


def test_efficiency_changes_energy_and_duration_together(v0,config):
    better=simulate(config,practice={"practice_loss":30},seed=42,days=2)
    assert better.latent_heats.kWh.iloc[0]==6200
    assert better.latent_heats.powered_min.iloc[0]==pytest.approx(74.4)
    assert better.latent_heats.nonpowered_min.iloc[0]==27
    assert v0.scenario_manifest["scenario_sha256"]==better.scenario_manifest["scenario_sha256"]


def test_invalid_schedule_demand_temperature_inventory_fail_closed(config):
    with pytest.raises(InvariantError):
        simulate(config,schedule={"D000_H01":1},days=2)
    for path,value in [("contract",1000),("rhf",1300),("inventory",201)]:
        changed=copy.deepcopy(config)
        target={"contract":changed["acceptance"]["contract_kva"],"rhf":changed["rhf"]["temp"],"inventory":changed["material"]["initial_yard"]}[path]
        target["value"]=value
        with pytest.raises(InvariantError):
            simulate(changed,days=2)


def test_validation_detects_corrupt_physical_ledger(v0):
    bad=copy.deepcopy(v0)
    idx=bad.latent_truth.index[bad.latent_truth.asset_id.eq("MAIN")][0]
    bad.latent_truth.loc[idx,"kWh"]+=1
    with pytest.raises(InvariantError,match="electrical_balance"):
        validate_simulation(bad)
