"""Adversarial model gates: legal inputs, grouped holdouts, replay and interfaces."""
import copy
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import joblib
import numpy as np
import pandas as pd
import pytest
from energy_copilot.common import ROOT, sha256, values
from energy_copilot.analytics.build import load_public_inputs, clean_readings, production_register, slot_table, heat_table
from energy_copilot.analytics.contracts import Contracts
from energy_copilot.forecast.contracts import Dataset, check_names, assert_available
from energy_copilot.forecast.datasets import direct_load_dataset, heat_dataset, health_features, HEAT_FEATURES
from energy_copilot.forecast.evaluation import failure_targets
from energy_copilot.forecast.uncertainty import residual_quantiles, prediction_quantiles, interval_metrics
from energy_copilot.forecast.interfaces import PredictionService

CORPUS=ROOT/"data/processed/training_v1"
MODELS=ROOT/"models/phase2b_v1"


def test_preflight_frozen_inputs_unchanged():
    manifest=json.loads((ROOT/"configs/phase2b_readonly_manifest.json").read_text())
    assert all(sha256(ROOT/p)==h for p,h in manifest.items())


@pytest.mark.parametrize("name",["latent_health","latent_fouling","true_severity","future_failure","future_event","fault_label","hidden_noise","UDI","Product ID","TWF","HDF","PWF","OSF","RNF","source_row_id","target","kWh","duration_min","actual_SEC","tap_temp_C","charge_t"])
def test_preflight_forbidden_names(name):
    with pytest.raises(ValueError):check_names([name])


def test_preflight_late_publication_aborts():
    origin=pd.Timestamp("2026-01-01")
    meta=pd.DataFrame(dict(forecast_origin=[origin],inputs_available_at=[origin+pd.Timedelta(minutes=15)],target_start=[origin]))
    with pytest.raises(ValueError):assert_available(meta)


def test_preflight_direct_horizons_are_origin_snapshots():
    times=pd.date_range("2026-01-01",periods=96*5,freq="15min")
    load=np.arange(len(times),dtype=float)
    def build(values):return direct_load_dataset(times,times+pd.Timedelta(minutes=15),values,"run",lambda _:"train")
    ds=build(load);changed=load.copy();changed[96:]+=10000;mutated=build(changed)
    origin=times[96];m=ds.meta.forecast_origin.eq(origin)
    pd.testing.assert_frame_equal(ds.X.loc[m],mutated.X.loc[m])
    for h in (1,4,96):
        row=ds.X.loc[m & ds.meta.horizon_slot.eq(h)].iloc[0]
        assert row.load_lag_1==95 and row.load_lag_96==0
        assert row.seasonal_naive==h-1
        assert row.load_past_4_mean==np.mean(load[92:96])
    assert ds.meta.loc[m,"source_max_available_at"].le(origin).all()


def test_preflight_positive_posting_delay_rejected():
    times=pd.date_range("2026-01-01",periods=96*3,freq="15min")
    with pytest.raises(ValueError,match="Late published"):
        direct_load_dataset(times,times+pd.Timedelta(minutes=20),np.ones(len(times)),"run",lambda _:"train")


def test_preflight_missing_inputs_preserved():
    times=pd.date_range("2026-01-01",periods=96*3,freq="15min")
    load=np.ones(len(times));load[95]=np.nan;load[100]=np.nan
    d=direct_load_dataset(times,times+pd.Timedelta(minutes=15),load,"run",lambda _:"train")
    assert d.X.load_lag_1.iloc[0]!=d.X.load_lag_1.iloc[0]
    assert not d.meta.target_start.eq(times[100]).any()
    assert np.isfinite(d.y).all()


def public_features():
    import yaml
    inputs=load_public_inputs(ROOT/"data/processed/sim_v1.1")
    cfg=values(yaml.safe_load((ROOT/"data/processed/analytics_v1/config_snapshot.yaml").read_text()))
    clean=clean_readings(inputs,cfg["parameters"]);prod=production_register(inputs,cfg["parameters"])
    slots,sfields=slot_table(clean,prod,inputs,cfg)
    heats,hfields=heat_table(inputs,slots,cfg)
    registry=Contracts(inputs.settings["timezone"]);registry.add("heat_features",heats,["heat_id"],hfields)
    return heats,slots,registry.schema


def test_preflight_heat_outcome_and_future_mutation():
    heats,slots,schema=public_features()
    e,d=heat_dataset(heats,schema,"r",42,"train",60.,10.)
    changed=heats.copy();changed.loc[20,"kWh"]*=20;changed.loc[20,"tap_temp_C"]*=2
    changed.loc[20,"duration_min"]*=2
    e2,d2=heat_dataset(changed,schema,"r",42,"train",60.,10.)
    pd.testing.assert_frame_equal(e.X,e2.X)
    assert not set(["kWh","duration_min","tap_temp_C","end_time","charge_t","liquid_t","chem_ok"])&set(e.X)
    X,meta=health_features(slots,"PMP_01","r",42,"train")
    changed=slots.copy();cut=slots.interval_end.iloc[1200]
    changed.loc[changed.interval_end.gt(cut),"PMP_01_vibration_mm_s"]=1000
    X2,meta2=health_features(changed,"PMP_01","r",42,"train")
    before=meta.forecast_origin.le(cut)
    pd.testing.assert_frame_equal(X.loc[before],X2.loc[before])


def test_preflight_features_never_read_events_or_hidden_files():
    original=pd.read_parquet
    def guarded(path,*args,**kwargs):
        assert not any(x in str(path) for x in ("latent","events","labels","targets"))
        return original(path,*args,**kwargs)
    with patch("pandas.read_parquet",side_effect=guarded):public_features()


def test_preflight_failure_label_window_and_censoring():
    origins=pd.to_datetime(["2026-01-01","2026-01-02","2026-01-03"])
    meta=pd.DataFrame(dict(forecast_origin=origins,target_end=origins+pd.Timedelta(hours=24)))
    events=pd.DataFrame(dict(asset_id=["PMP_01"],type=["failure"],start=[pd.Timestamp("2026-01-02")]))
    y,_=failure_targets(meta,events,"PMP_01")
    assert list(y)==[1,0,0]  # at origin is already happened; at horizon end is positive


def test_preflight_interval_math_and_ordering():
    residual=np.arange(-100,101)
    cal=residual_quantiles(residual,np.zeros(len(residual)))
    q=prediction_quantiles(np.ones(201)*150,cal)
    assert (q["p10"]<=q["p50"]).all() and (q["p50"]<=q["p90"]).all()
    score=interval_metrics(residual+150,q)
    expected=np.mean((residual+150>=q["p10"])&(residual+150<=q["p90"]))
    assert score["actual_two_sided_coverage"]==expected
    assert score["actual_upper_coverage"]==np.mean(residual+150<=q["p90"])


@pytest.fixture(scope="module")
def trained():
    assert (MODELS/"prediction_contract.json").exists(),"Run python -m scripts.phase2b before release tests"
    return PredictionService(MODELS)


def heat_context():
    ds=Dataset.read(CORPUS/"datasets/heat_energy")
    i=ds.meta.index[ds.meta.split.eq("test") & ds.meta.practice_loss_kWh_t.eq(60.)][10]
    origin=ds.meta.forecast_origin.iloc[i]
    return dict(heat_id=str(ds.meta.heat_id.iloc[i]),forecast_origin=origin,candidate_start=origin,
                features=ds.X.iloc[i].to_dict(),available_at={c:origin for c in ds.X})


def test_interface_heat_deterministic_finite_ordered(trained):
    context=heat_context();a=trained.predict_heat(context);b=trained.predict_heat(context)
    assert a==b and a.status=="model"
    assert 0<=a.energy_p10_kWh<=a.energy_p50_kWh<=a.energy_p90_kWh
    assert 0<a.duration_p10_min<=a.duration_p50_min<=a.duration_p90_min
    assert np.isfinite([a.energy_p50_kWh,a.duration_p50_min,a.SEC_p50]).all()
    assert a.SEC_p50==a.energy_p50_kWh/10


def test_interface_schema_and_availability_fail_closed(trained):
    context=heat_context();context["features"]["latent_health"]=.8
    with pytest.raises(ValueError):trained.predict_heat(context)
    context=heat_context();context["available_at"]["previous_heat_SEC"]=context["forecast_origin"]+pd.Timedelta(minutes=1)
    with pytest.raises(ValueError):trained.predict_heat(context)
    context=heat_context();context["features"]["candidate_liquid_t"]=12.
    with pytest.raises(ValueError):trained.predict_heat(context)
    with pytest.raises(ValueError):trained.predict_heat(heat_context(),"best-safe")
    context=heat_context();context["features"]["previous_heat_SEC"]="650"
    with pytest.raises(ValueError,match="type mismatch"):trained.predict_heat(context)


def test_interface_explicit_fallback(trained):
    absent={MODELS/"heat_energy/production.joblib",MODELS/"heat_duration/production.joblib"}
    exists=Path.exists
    # Simulate unavailable artifacts without deleting or rewriting evidence.
    with patch.object(Path,"exists",lambda p:False if p in absent else exists(p)):
        prediction=trained.predict_heat(heat_context())
    assert prediction.status=="fallback" and not prediction.usable_for_constraints
    assert prediction.energy_p90_kWh>=prediction.energy_p50_kWh>0


def test_interfaces_health_and_load(trained):
    d=Dataset.read(CORPUS/"datasets/health_PMP_01");i=d.meta.index[d.meta.split.eq("test")][100];origin=d.meta.forecast_origin.iloc[i]
    c=dict(asset_id="PMP_01",forecast_origin=origin,features=d.X.iloc[i].to_dict(),available_at={f:origin for f in d.X})
    a=trained.predict_health(c,24);assert a==trained.predict_health(c,24)
    assert 0<=a.failure_probability<=1 and 0<=a.calibrated_probability<=1
    with pytest.raises(ValueError):trained.predict_health(c,48)
    d=Dataset.read(CORPUS/"datasets/load");m=d.meta.split.eq("test");origin=d.meta.loc[m,"forecast_origin"].iloc[0]
    indices=d.meta.index[m & d.meta.forecast_origin.eq(origin)]
    # Missing targets do not remove known prior-day inputs; reconstruct the full public snapshot.
    folder=CORPUS/"runs"/str(d.meta.run_id.iloc[indices[0]])
    inputs=load_public_inputs(folder)
    import yaml
    cfg=values(yaml.safe_load((ROOT/"configs/analytics_v1.yaml").read_text()))
    clean=clean_readings(inputs,cfg["parameters"])
    r=clean.loc[clean.asset_id.eq("AUX")].set_index("timestamp")
    row=d.X.iloc[indices[0]].to_dict()
    for col in ("seasonal_naive","horizon_slot","target_hour","target_weekday","target_shift","target_sin","target_cos"):row.pop(col)
    profile=[dict(value=r.kW.loc[origin-pd.Timedelta(days=1)+pd.Timedelta(minutes=15*j)],available_at=origin-pd.Timedelta(days=1)+pd.Timedelta(minutes=15*(j+1))) for j in range(96)]
    c=dict(features=row,available_at={f:origin for f in row},seasonal_profile=profile)
    a=trained.predict_background_load(origin,96,c);assert a==trained.predict_background_load(origin,96,c)
    assert len(a)==96 and all(p.components==("AUX",) for p in a)
    assert all(0<=p.load_p10_kW<=p.load_p50_kW<=p.load_p90_kW for p in a)
    assert all(pd.Timestamp(p.available_at)<=pd.Timestamp(p.interval_start) for p in a)
    c["seasonal_profile"][95]["available_at"]=origin+pd.Timedelta(minutes=1)
    with pytest.raises(ValueError):trained.predict_background_load(origin,96,c)


@pytest.mark.parametrize("task",["heat_energy","heat_duration","load","health_MILL_01","health_PMP_01"])
def test_training_dataset_audit_and_separation(task,trained):
    d=Dataset.read(CORPUS/"datasets"/task);assert d.audit()["status"]=="PASS"
    assert d.meta.groupby("seed").split.nunique().max()==1
    for _,g in d.meta.groupby("run_id"):assert g.forecast_origin.is_monotonic_increasing
    assert not set(d.X)&set(d.meta) - {"practice_loss_kWh_t","horizon_slot"}
    if task=="load":assert d.meta.source_max_available_at.le(d.meta.forecast_origin).all()


def test_episode_groups_not_mixed(trained):
    labels=pd.read_parquet(CORPUS/"evaluation/failure_episodes.parquet")
    assert labels.groupby(["seed","asset_id","episode_id"]).split.nunique().max()==1


def test_serialization_reload_and_fitted_training_replay(trained):
    for path in MODELS.rglob("production.joblib"):
        bundle=joblib.load(path);assert bundle["features"]
        summary=json.loads((path.parent/"metadata.json").read_text())
        assert all(summary["deterministic_training"].values())
        assert "preprocessing" in bundle["model"].named_steps if hasattr(bundle["model"],"named_steps") else True
    assert PredictionService(MODELS).predict_heat(heat_context())==trained.predict_heat(heat_context())


def test_reference_health_probability_calibration_and_skill(trained):
    for asset in ("MILL_01","PMP_01"):
        metadata=json.loads((MODELS/f"health/{asset}/metadata.json").read_text())
        assert metadata["calibrated_test"]["Brier"]<metadata["no_skill_Brier"]
        assert metadata["calibrated_test"]["PR_AUC"]>metadata["calibrated_test"]["prevalence"]
        assert len(metadata["calibrated_test"]["calibration_bins"])>=3


def test_regression_uncertainty_observed_coverage(trained):
    # Independent arithmetic must agree with the published coverage; no post-hoc
    # nominal-coverage tolerance turns a calibration discrepancy into a PASS.
    for task in ("heat_energy","heat_duration","load"):
        p=pd.read_parquet(MODELS/task/"test_predictions.parquet")
        score=interval_metrics(p.actual,{q:p[q].to_numpy() for q in ("p10","p50","p90")})
        published=json.loads((MODELS/task/"metadata.json").read_text())["interval"]
        assert score["actual_two_sided_coverage"]==published["actual_two_sided_coverage"]
        assert score["actual_upper_coverage"]==published["actual_upper_coverage"]



def test_predictors_train_only_preprocessing_and_target_exclusion(trained):
    for task in ("heat_energy","heat_duration","load","health_MILL_01","health_PMP_01"):
        d=Dataset.read(CORPUS/"datasets"/task)
        folder=MODELS/("health/"+task.removeprefix("health_") if task.startswith("health") else task)
        model=joblib.load(folder/"linear.joblib")
        imputer=model.named_steps["preprocessing"].named_transformers_["numeric"].named_steps["impute"]
        train=d.X.loc[d.meta.split.eq("train")]
        expected=train.median().fillna(0).to_numpy()
        np.testing.assert_allclose(imputer.statistics_,expected)
        assert "target" not in d.X


def test_public_external_splits_and_features(trained):
    ai=Dataset.read(CORPUS/"external/ai4i");assert ai.audit()["status"]=="PASS"
    assert len(ai.X)==10000 and len(ai.X.columns)==6
    uci=Dataset.read(CORPUS/"external/uci")
    assert uci.meta.loc[uci.meta.split.eq("train"),"target_start"].dt.month.max()==8
    assert set(uci.meta.loc[uci.meta.split.eq("validation"),"target_start"].dt.month)=={9}
    assert set(uci.meta.loc[uci.meta.split.eq("calibration"),"target_start"].dt.month)=={10}
    assert set(uci.meta.loc[uci.meta.split.eq("test"),"target_start"].dt.month)=={11,12}
    assert not any("CO2" in c or "Factor" in c or "Reactive" in c for c in uci.X)


def test_corpus_physical_gates_and_hashes(trained):
    runs=json.loads((CORPUS/"runs.json").read_text())
    assert len(runs)==50 and len({r["seed"] for r in runs})==25
    assert all(r["physical"]["violations"]==0 for r in runs)
    manifest=json.loads((CORPUS/"dataset_manifest.json").read_text())
    assert all(sha256(CORPUS/n)==h for n,h in manifest["hashes"].items())
