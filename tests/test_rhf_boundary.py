"""Regression gates for the shared-noise latent-fouling oracle (B01)."""
import importlib

import pandas as pd
import pytest

from energy_copilot.common import ROOT, load_config
from energy_copilot.sim import simulate
from scripts.rhf_boundary import temperature_boundary, assert_b01_resolved

TABLES = ("readings", "heats", "production", "events", "latent_truth", "latent_heats")


@pytest.fixture(scope="module")
def successor():
    return simulate(days=30, seed=42)


def test_independent_residuals_attack_rejected_and_signal_retained(successor):
    metrics = temperature_boundary(successor.readings, successor.latent_truth, successor.config)
    assert_b01_resolved(metrics, successor.config["observations"]["sensor_noise"]["value"])


def test_regression_gate_detects_legacy_algebraic_oracle():
    old = ROOT / "data/processed/sim_v1.0"
    metrics = temperature_boundary(pd.read_parquet(old / "readings.parquet"),
                                   pd.read_parquet(old / "latent_truth.parquet"),
                                   load_config(old / "config_snapshot.yaml"))
    assert metrics["median_error"] < 1e-12
    assert metrics["max_error"] < 1e-12
    with pytest.raises(AssertionError, match="near-exact"):
        assert_b01_resolved(metrics, .005)


def test_exact_frozen_physics_accounting_labels_and_other_observations(successor):
    old = ROOT / "data/processed/sim_v1.0"
    cfg = load_config(old / "config_snapshot.yaml")
    cfg["version"] = successor.config["version"]
    assert cfg == successor.config  # All numeric values and assumptions unchanged.
    for name in TABLES[1:]:
        pd.testing.assert_frame_equal(getattr(successor, name), pd.read_parquet(old / f"{name}.parquet"),
                                      check_exact=True)
    prior = pd.read_parquet(old / "readings.parquet")
    rhf = prior.asset_id.eq("RHF_01")
    pd.testing.assert_frame_equal(successor.readings.loc[~rhf], prior.loc[~rhf], check_exact=True)
    pd.testing.assert_frame_equal(successor.readings.drop(columns=["temp_C", "flue_temp_C"]),
                                  prior.drop(columns=["temp_C", "flue_temp_C"]), check_exact=True)


def test_changing_flue_stream_cannot_shift_zone_or_other_randomness(monkeypatch):
    baseline = simulate(days=2)
    module = importlib.import_module("energy_copilot.sim.scenario")
    monkeypatch.setattr(module, "RHF_FLUE_STREAM", "rhf_flue_temperature_isolation_test")
    changed = simulate(days=2)
    for name in TABLES[1:]:
        pd.testing.assert_frame_equal(getattr(baseline, name), getattr(changed, name), check_exact=True)
    pd.testing.assert_frame_equal(baseline.readings.drop(columns="flue_temp_C"),
                                  changed.readings.drop(columns="flue_temp_C"), check_exact=True)
    assert not baseline.readings.flue_temp_C.equals(changed.readings.flue_temp_C)


def test_successor_same_seed_identity_and_different_seed_variation(successor):
    replay = simulate(days=30, seed=42)
    for name in TABLES:
        pd.testing.assert_frame_equal(getattr(successor, name), getattr(replay, name), check_exact=True)
    assert successor.scenario_manifest == replay.scenario_manifest
    different = simulate(days=30, seed=43)
    assert not successor.readings.equals(different.readings)
    assert not successor.latent_heats.equals(different.latent_heats)
