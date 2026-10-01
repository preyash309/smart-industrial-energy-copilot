"""Phase-II-A release gates: public accounting, causality and legal availability."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import yaml

from energy_copilot.common import ROOT, sha256, values
from energy_copilot.analytics import build_analytics, load_public_inputs, select_predictors, load_predictors
from energy_copilot.analytics.build import clean_readings, slot_table, production_register, heat_table, accounting_checks
from energy_copilot.analytics.contracts import validate_feature_table


@pytest.fixture(scope="module")
def inputs():
    return load_public_inputs(ROOT / "data/processed/sim_v1.1")


@pytest.fixture(scope="module")
def result(inputs):
    return build_analytics(inputs)


def test_phase1_frozen_files_and_simulator_unchanged():
    snapshot = json.loads((ROOT / "configs/phase1_readonly_manifest.json").read_text())
    assert all(sha256(ROOT/name)==digest for name, digest in snapshot.items())
    for version in ("sim_v1.0", "sim_v1.1"):
        folder = ROOT / "data/processed" / version
        manifest = json.loads((folder / "freeze_manifest.json").read_text())
        assert all(sha256(folder/name)==digest for name,digest in manifest["hashes"].items())


def test_public_energy_and_production_accounting(result, inputs):
    a = result.accounting
    assert a["status"]=="PASS"
    assert max(a["production_max_mass_residual_t"].values())<1e-8
    assert max(a["heat_to_shift_mass_residual_t"].values())<1e-8
    energy = a["noisy_energy"]
    assert energy["common_slots"]>2700
    assert energy["median_absolute_relative_residual"]<.02
    assert energy["residual_common_kWh"]!=0  # Never force noisy meters to balance.
    daily = result.tables["asset_daily_metrics"]
    d = daily[daily.asset_id.eq("MAIN")]
    assert d.bar_t.sum()==pytest.approx(inputs.production.bar_t.sum())
    assert d.billet_t.sum()==pytest.approx(inputs.heats.billet_t.sum())
    shares = daily[~daily.asset_id.eq("MAIN")].groupby("date").feeder_mix_share_common_all.sum()
    np.testing.assert_allclose(shares,1)


def test_sec_duration_residual_and_mass_normalization(result):
    h = result.tables["heat_features"]
    np.testing.assert_allclose(h.SEC_kWh_per_t,h.kWh/h.liquid_t)
    np.testing.assert_allclose(h.duration_min,(h.end_time-h.start_time).dt.total_seconds()/60)
    np.testing.assert_allclose(h.residual_SEC,h.actual_SEC-h.expected_SEC,equal_nan=True)
    d = result.tables["asset_daily_metrics"]
    producing = d.bar_t>0
    np.testing.assert_allclose(d.loc[producing,"electricity_kWh_per_t_bar"],d.loc[producing,"energy_best_kWh"]/d.loc[producing,"bar_t"])
    assert d.loc[~producing,"electricity_kWh_per_t_bar"].isna().all()


def test_backward_slot_lags_rollings_and_counts(result):
    s = result.tables["slot_features"]
    for lag in (1,4,96):
        pd.testing.assert_series_equal(s[f"MAIN_kW_lag_{lag}"],s.MAIN_kW.shift(lag),check_names=False)
    for window in (4,96):
        reference = s.MAIN_kW.shift(1).rolling(window,min_periods=1)
        pd.testing.assert_series_equal(s[f"MAIN_kW_past_{window}_mean"],reference.mean(),check_names=False)
        pd.testing.assert_series_equal(s[f"MAIN_kW_past_{window}_count"],reference.count(),check_names=False)
    assert s.MAIN_kW_lag_1.iloc[0]!=s.MAIN_kW_lag_1.iloc[0]


def test_prefix_invariance_under_future_meter_mutation(inputs, result):
    config = values(result.config); clean = clean_readings(inputs,config["parameters"])
    production = production_register(inputs,config["parameters"])
    original,_ = slot_table(clean,production,inputs,config)
    cutoff = original.interval_start.iloc[1500]
    changed = clean.copy(); changed.loc[changed.timestamp.ge(cutoff),"kW"]*=2
    changed.loc[changed.timestamp.ge(cutoff),"kWh"]*=2
    altered,_ = slot_table(changed,production,inputs,config)
    pd.testing.assert_frame_equal(original.loc[original.interval_start.lt(cutoff)],altered.loc[altered.interval_start.lt(cutoff)])
    # Current-slot mutation must not enter that slot's start-time predictors.
    before = select_predictors(original,"slot_features",result.schema,"slot_load_at_start")
    after = select_predictors(altered,"slot_features",result.schema,"slot_load_at_start")
    pd.testing.assert_frame_equal(before.iloc[:1501],after.iloc[:1501])


def test_heat_baseline_only_prior_completed_heats(result):
    h = result.tables["heat_features"]
    assert h.expected_SEC.iloc[:8].isna().all()
    for row in h.itertuples():
        prior = h[h.available_at.le(row.start_time) & h.heat_id.ne(row.heat_id)]
        assert row.history_count==len(prior)
        if len(prior):
            assert row.previous_heat_SEC==pytest.approx(prior.SEC_kWh_per_t.iloc[-1])
            assert row.global_mean_SEC==pytest.approx(prior.SEC_kWh_per_t.mean())
            assert row.previous_heat_available_at<=row.start_time


def test_current_heat_outcome_cannot_change_own_forecast(inputs,result):
    changed = copy.deepcopy(inputs)
    ix = 140
    changed.heats.loc[ix:,"kWh"]*=4
    cfg = values(result.config)
    altered,_ = heat_table(changed,result.tables["slot_features"],cfg)
    original = result.tables["heat_features"]
    before = select_predictors(original,"heat_features",result.schema,"heat_energy")
    after = select_predictors(altered,"heat_features",result.schema,"heat_energy")
    pd.testing.assert_frame_equal(before.iloc[:ix+1],after.iloc[:ix+1])


def test_availability_and_completed_heat_to_slot_join(result):
    s = result.tables["slot_features"]; h = result.tables["heat_features"]
    assert (s.interval_end-s.interval_start).eq(pd.Timedelta(minutes=15)).all()
    assert s.available_at.eq(s.interval_end).all()
    assert h.available_at.eq(h.end_time).all()
    assert (h.context_available_at.isna() | h.context_available_at.le(h.start_time)).all()
    assert (s.production_report_available_at<=s.interval_start).all()
    for heat in h.dropna(subset=["context_available_at"]).itertuples():
        candidates = s[s.available_at.le(heat.start_time)]
        latest = candidates.iloc[-1]
        assert heat.context_available_at==latest.available_at
        assert heat.context_MAIN_kW==pytest.approx(latest.MAIN_kW,nan_ok=True)
    cutoff = pd.Timestamp("2026-01-05 08:00")
    previous = s[s.interval_start.eq(cutoff-pd.Timedelta(minutes=15))].iloc[0]
    published = s[s.interval_start.eq(cutoff)].iloc[0]
    assert previous.billet_inventory_t==50
    assert published.billet_inventory_t==24
    assert published.inventory_age_min==0
    assert previous.rolling_output_last_shift_t!=previous.rolling_output_last_shift_t


def test_nonzero_posting_delay_is_enforced(inputs,result):
    cfg = copy.deepcopy(result.config); cfg["parameters"]["publication_delay_minutes"]["value"]=5
    resolved = values(cfg); clean = clean_readings(inputs,resolved["parameters"])
    prod = production_register(inputs,resolved["parameters"])
    slots,fields = slot_table(clean,prod,inputs,resolved)
    schema = copy.deepcopy(result.schema)
    # Values/types unchanged; use the contract derived for delayed availability.
    for col in fields: schema["tables"]["slot_features"]["columns"][col].update(fields[col])
    x = select_predictors(slots,"slot_features",schema,"slot_load_at_start",columns=["MAIN_kW_lag_1","MAIN_kW_lag_4"])
    assert x.MAIN_kW_lag_1.isna().all()  # Previous interval posts five minutes after origin.
    assert x.MAIN_kW_lag_4.notna().any()


def test_schema_roles_no_hidden_or_fault_label_leakage(result,inputs):
    for name,frame in result.tables.items():
        assert validate_feature_table(frame,name,result.schema)
        assert not any(token in col.lower() for col in frame for token in ("latent_","fault_label","severity","future_failure","future_event","health","random_"))
    h = select_predictors(result.tables["heat_features"],"heat_features",result.schema,"heat_energy")
    assert not {"kWh","SEC_kWh_per_t","actual_SEC","residual_SEC","duration_min","end_time","liquid_t","billet_t","tap_temp_C","chem_ok","charge_t"}&set(h)
    with pytest.raises(ValueError,match="allowlist"):
        select_predictors(result.tables["heat_features"],"heat_features",result.schema,"heat_energy",columns=["kWh"])
    corrupt = result.tables["heat_features"].assign(latent_fouling=1.)
    with pytest.raises(ValueError): validate_feature_table(corrupt,"heat_features",result.schema)
    with pytest.raises(ValueError): select_predictors(result.tables["diagnostic_candidates"],"diagnostic_candidates",result.schema,"heat_energy")


def test_quality_missing_power_fallback_and_no_backward_fill(inputs,result):
    clean = clean_readings(inputs,values(result.config)["parameters"])
    flagged = inputs.readings.sensor_glitch
    assert clean.loc[flagged,"kWh"].isna().all()
    assert clean.loc[flagged,"kW"].isna().all()
    fallback = clean.energy_method.eq("same_interval_power")
    assert fallback.any()
    np.testing.assert_allclose(clean.loc[fallback,"energy_best_kWh"],clean.loc[fallback,"kW"]*.25)
    assert clean.loc[flagged,"energy_best_kWh"].isna().all()
    assert clean.loc[clean.energy_method.eq("missing"),"energy_best_kWh"].isna().all()
    assert result.tables["slot_features"].IF_01_flow_m3_h.isna().all()  # Not applicable.


def test_regeneration_byte_identical_and_loader_file_boundary(result,inputs):
    tmp_path = ROOT / "data/runs/analytics_test_replay"
    again = build_analytics(inputs)
    first = tmp_path / "first"; second=tmp_path / "second"
    result.write(first); again.write(second)
    for path in first.iterdir(): assert sha256(path)==sha256(second/path.name)
    predictor = load_predictors(first,"heat_features","heat_energy")
    assert len(predictor)==338
    with pytest.raises(ValueError): load_predictors(first,"events","heat_energy")


def test_pipeline_never_reads_hidden_or_event_tables(inputs):
    real = pd.read_parquet; reads=[]
    def public_only(path,*args,**kwargs):
        reads.append(Path(path).name)
        assert Path(path).name in {"readings.parquet","heats.parquet","production.parquet"}
        return real(path,*args,**kwargs)
    with patch("pandas.read_parquet",side_effect=public_only): build_analytics()
    assert set(reads)=={"readings.parquet","heats.parquet","production.parquet"}


def test_observable_diagnostic_evidence(result):
    alerts = result.tables["diagnostic_candidates"]
    assert len(alerts)>0
    assert {"high_heat_SEC","high_temperature_and_energy","compressor_mill_off_load","machine_power_deviation"}<=set(alerts.rule)
    np.testing.assert_allclose(alerts.residual,alerts.measured_value-alerts.expected_value)
    assert alerts.available_at.eq(alerts.timestamp).all()
    for value in alerts.evidence_json:
        evidence = json.loads(value)
        assert not {"fault_label","latent_fouling","latent_wear","true_fault_severity"}&set(evidence)


def test_full_shift_is_unavailable_before_close(result):
    p = result.tables["production_register"]
    assert p.available_at.eq(p.interval_end).all()
    d = result.tables["asset_daily_metrics"]
    early = select_predictors(d,"asset_daily_metrics",result.schema,"asset_next_day_risk",forecast_origins=d.interval_end-pd.Timedelta(seconds=1),columns=["energy_best_kWh"])
    assert early.energy_best_kWh.isna().all()
    assert early.inputs_available_at.isna().all()
