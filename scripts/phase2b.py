"""Reproducible Phase-II-B runner. Frozen Phase I/II-A are read-only inputs."""
import argparse
import json
import platform
import warnings
from pathlib import Path
import importlib.metadata
import numpy as np
import pandas as pd
import yaml
from threadpoolctl import threadpool_limits
from energy_copilot.common import ROOT, values, sha256, canonical_hash, write_json, validate_parameters
from energy_copilot.analytics.build import load_public_inputs, clean_readings, production_register, slot_table, heat_table, accounting_checks
from energy_copilot.analytics.contracts import Contracts, select_predictors
from energy_copilot.forecast.contracts import Dataset, check_names
from energy_copilot.forecast.datasets import heat_dataset, direct_load_dataset, health_features, concatenate, HEAT_FEATURES
from energy_copilot.forecast.evaluation import failure_targets
from energy_copilot.forecast.models import fit_regression, fit_health
from scripts.phase2b_setup import setup

CORPUS=ROOT/"data/processed/training_v1"
MODELS=ROOT/"models/phase2b_v1"


def protected():
    hashes=json.loads((ROOT/"configs/phase2b_readonly_manifest.json").read_text())
    bad=[name for name,digest in hashes.items() if not (ROOT/name).exists() or sha256(ROOT/name)!=digest]
    if bad:raise ValueError(f"Frozen input changed: {bad}")
    return {"status":"PASS","protected_files":len(hashes)}


def preflight():
    result=protected()
    d=ROOT/"data/processed/analytics_v1"
    schema=yaml.safe_load((d/"feature_schema.yaml").read_text())
    available=yaml.safe_load((d/"feature_availability.yaml").read_text())
    h=pd.read_parquet(d/"heat_features.parquet")
    selected=select_predictors(h,"heat_features",schema,"heat_energy",columns=HEAT_FEATURES)
    check_names(HEAT_FEATURES)
    assert (selected.inputs_available_at.isna()|selected.inputs_available_at.le(selected.forecast_origin)).all()
    for f in HEAT_FEATURES:
        assert available["tables"]["heat_features"][f]["available_at"]==schema["tables"]["heat_features"]["columns"][f]["available_at"]
    result.update(heat_predictor_allowlist="PASS",availability_schema_agreement="PASS",events_and_latent_predictors="ABSENT")
    CORPUS.mkdir(parents=True,exist_ok=True)
    write_json(CORPUS/"pretraining_audit.json",result)
    return result


def store_run(sim,folder):
    if folder.exists():raise ValueError("Refuse to overwrite generated scenario")
    folder.mkdir(parents=True);evaluation=folder/"evaluation";evaluation.mkdir()
    for name in ("readings","heats","production"):
        getattr(sim,name).to_parquet(folder/f"{name}.parquet",index=False)
    for name in ("events","latent_truth","latent_heats"):
        getattr(sim,name).to_parquet(evaluation/f"{name}.parquet",index=False)
    write_json(folder/"scenario_manifest.json",sim.scenario_manifest)
    write_json(folder/"simulation_summary.json",sim.summary)
    (folder/"config_snapshot.yaml").write_text(yaml.safe_dump(sim.config,sort_keys=False),encoding="utf-8")
    (folder/"schema.yaml").write_bytes((ROOT/"data/processed/sim_v1.1/schema.yaml").read_bytes())
    # Evaluation reads hidden truth only AFTER public observations are generated.
    from scripts.independent_accounting import independent
    metrics,checks,errors=independent({k:getattr(sim,k) for k in ("latent_truth","latent_heats","production","events")},sim.config)
    if sum(checks.values())!=0:raise ValueError(f"Independent physical constraint failure: {checks}")
    write_json(evaluation/"independent_checks.json",dict(metrics=metrics,checks=checks,errors=errors))
    write_json(folder/"source_hashes.json",{str(p.relative_to(folder)).replace('\\','/'):sha256(p) for p in sorted(folder.rglob('*')) if p.is_file()})
    return metrics


def build_corpus(cfg):
    existing=CORPUS/"dataset_manifest.json"
    if existing.exists():
        manifest=json.loads(existing.read_text())
        if manifest["config_sha256"]!=canonical_hash(cfg):raise ValueError("Corpus config mismatch; choose a new version")
        for name,digest in manifest["hashes"].items():
            if sha256(CORPUS/name)!=digest:raise ValueError("Training data hash mismatch")
        return manifest
    from energy_copilot.sim import simulate
    plant=yaml.safe_load((ROOT/"data/processed/sim_v1.1/config_snapshot.yaml").read_text())
    analytical=yaml.safe_load((ROOT/"data/processed/analytics_v1/config_snapshot.yaml").read_text())
    resolved=values(analytical);par=cfg["parameters"]
    collection={k:[] for k in ("heat_energy","heat_duration","load","health_MILL_01","health_PMP_01")}
    runs=[];episodes=[]
    for split,seeds in cfg["seeds"].items():
        for seed in seeds:
            for mode,modecfg in cfg["practice_modes"].items():
                run_id=f"seed_{seed}_{mode}";folder=CORPUS/"runs"/run_id
                practice=None if mode=="normal" else {"practice_loss":modecfg["practice_loss"]}
                if folder.exists():
                    hashes=json.loads((folder/"source_hashes.json").read_text())
                    if any(sha256(folder/n)!=h for n,h in hashes.items()):raise ValueError("Scenario changed")
                    metrics=json.loads((folder/"evaluation/independent_checks.json").read_text())["metrics"]
                else:
                    sim=simulate(config=plant,practice=practice,seed=seed,days=par["days"])
                    metrics=store_run(sim,folder)
                    del sim
                public=load_public_inputs(folder)
                clean=clean_readings(public,resolved["parameters"])
                production=production_register(public,resolved["parameters"])
                slots,sfields=slot_table(clean,production,public,resolved)
                heats,hfields=heat_table(public,slots,resolved)
                registry=Contracts(public.settings["timezone"])
                registry.add("heat_features",heats,["heat_id"],hfields)
                registry.add("slot_features",slots,["interval_start"],sfields)
                accounting=accounting_checks(clean,public,resolved)
                energy,duration=heat_dataset(heats,registry.schema,run_id,seed,split,modecfg["practice_loss"],values(plant)["if"]["liquid_per_heat"])
                collection["heat_energy"].append(energy);collection["heat_duration"].append(duration)
                if mode=="normal":
                    load=direct_load_dataset(slots.interval_start,slots.available_at,slots.AUX_kW,run_id,lambda _:split,
                                             par["load_horizon_slots"],par["load_lags"],par["load_windows"])
                    load.meta["seed"]=seed;collection["load"].append(load)
                    # Evaluation events cannot enter the feature function's arguments.
                    events=pd.read_parquet(folder/"evaluation/events.parquet")
                    for asset in cfg["health_assets"]:
                        X,meta=health_features(slots,asset,run_id,seed,split,par["health_horizon_hours"],par["health_stride_slots"])
                        y,episode=failure_targets(meta,events,asset)
                        collection[f"health_{asset}"].append(Dataset(X,meta,y))
                        labels=meta[["row_id","run_id","seed","split","asset_id"]].copy();labels["episode_id"]=episode;labels["target"]=y
                        episodes.append(labels)
                runs.append(dict(run_id=run_id,seed=seed,split=split,practice_mode=mode,physical=metrics,
                                 public_accounting=accounting,scenario_manifest=json.loads((folder/"scenario_manifest.json").read_text())))
                print(f"validated {run_id}: {len(heats)} heats, {metrics['violations']} physical violations",flush=True)
    audits={}
    for name,parts in collection.items():
        ds=concatenate(parts)
        # Remove sensor channels with no information in TRAIN only; keep the decision independent of test.
        if name.startswith("health"):
            train=ds.X.loc[ds.meta.split.eq("train")]
            keep=[c for c in ds.X if train[c].nunique(dropna=True)>1]
            ds.X=ds.X[keep]
        audits[name]=ds.audit();ds.write(CORPUS/"datasets"/name)
    labels=CORPUS/"evaluation";labels.mkdir(exist_ok=True)
    pd.concat(episodes,ignore_index=True).to_parquet(labels/"failure_episodes.parquet",index=False)
    write_json(CORPUS/"split_manifest.json",dict(seed=par["seed"],partitions=cfg["seeds"],practice_variants_grouped=True,
                                               selection="validation",uncertainty_and_probability_fit="calibration",final_untouched="test",runs=[{k:r[k] for k in ("run_id","seed","split","practice_mode")} for r in runs]))
    (CORPUS/"config_snapshot.yaml").write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
    write_json(CORPUS/"runs.json",runs)
    manifest=dict(version="training_v1",source_version="sim_v1.1",config_sha256=canonical_hash(cfg),audits=audits,
                  run_count=len(runs),seed_count=sum(map(len,cfg["seeds"].values())),
                  hashes={str(p.relative_to(CORPUS)).replace('\\','/'):sha256(p) for p in sorted(CORPUS.rglob('*')) if p.is_file() and p.name!="pretraining_audit.json"})
    write_json(existing,manifest)
    return manifest


def external_datasets(cfg):
    steel=pd.read_parquet(ROOT/"data/interim/uci_steel_clean.parquet")
    frozen=pd.read_parquet(ROOT/"data/interim/uci_steel_split_manifest.parquet")
    if not steel.source_row_id.equals(frozen.source_row_id) or not steel.timestamp.equals(frozen.timestamp):raise ValueError("UCI split join failed")
    def split(t):return "train" if t.month<=8 else "validation" if t.month==9 else "calibration" if t.month==10 else "test"
    uci=direct_load_dataset(steel.timestamp,steel.interval_end,steel.Usage_kWh,"uci_steel",split,
                            cfg["parameters"]["load_horizon_slots"],cfg["parameters"]["load_lags"],cfg["parameters"]["load_windows"])
    # The frozen outer Jan-Aug / Sep-Oct / Nov-Dec split is unchanged.
    # Validation is internally divided chronologically: September selection, October calibration.
    ai=pd.read_parquet(ROOT/"data/interim/ai4i_clean.parquet")
    split_manifest=pd.read_parquet(ROOT/"data/interim/ai4i_split_manifest.parquet")
    contract=json.loads((ROOT/"data/interim/ai4i_feature_contract.json").read_text())
    if not ai.source_row_id.equals(split_manifest.source_row_id):raise ValueError("AI4I split join failed")
    parts=split_manifest.split.copy()
    # Stratified inner selection/calibration halves of the already-frozen validation set.
    from sklearn.model_selection import train_test_split
    ids=ai.index[parts.eq("validation")]
    selection,cal=train_test_split(ids,test_size=.5,stratify=ai.loc[ids,"Machine failure"],random_state=cfg["parameters"]["seed"])
    parts.loc[cal]="calibration"
    meta=pd.DataFrame(dict(row_id="ai4i:"+ai.source_row_id.astype(str),run_id="ai4i",split=parts,snapshot_available=True))
    ai_dataset=Dataset(ai[contract["features"]].copy(),meta,ai["Machine failure"])
    for name,ds in (("uci",uci),("ai4i",ai_dataset)):
        ds.audit();ds.write(CORPUS/"external"/name)
    return uci,ai_dataset


def train(cfg,manifest):
    par=dict(cfg["parameters"],version=cfg["version"]); results={}
    MODELS.mkdir(parents=True,exist_ok=True)
    with threadpool_limits(limits=1):
        for name in ("heat_energy","heat_duration","load","health_MILL_01","health_PMP_01"):
            dataset=Dataset.read(CORPUS/"datasets"/name)
            if name.startswith("health"):
                folder=MODELS/"health"/name.removeprefix("health_");result,pred=fit_health(dataset,name,folder,par)
            else:result,pred=fit_regression(dataset,name,MODELS/name,par,load=name=="load")
            results[name]=result
            print(f"selected {name}: {result['selected']}",flush=True)
        uci,ai=external_datasets(cfg)
        results["uci"],_=fit_regression(uci,"uci",MODELS/"external/uci",par,load=True)
        results["ai4i"],_=fit_health(ai,"ai4i",MODELS/"external/ai4i",par)
    preds=ROOT/"predictions";preds.mkdir(exist_ok=True)
    e=pd.read_parquet(MODELS/"heat_energy/test_predictions.parquet")
    d=pd.read_parquet(MODELS/"heat_duration/test_predictions.parquet")
    assert e.row_id.equals(d.row_id)
    e=e.rename(columns={q:f"energy_{q}_kWh" for q in ("p10","p50","p90")})
    for q in ("p10","p50","p90"):e[f"duration_{q}_min"]=d[q]
    candidate_t=values(yaml.safe_load((ROOT/"data/processed/sim_v1.1/config_snapshot.yaml").read_text()))["if"]["liquid_per_heat"]
    e["SEC_p50"]=e.energy_p50_kWh/candidate_t;e["available_at"]=e.forecast_origin
    e["practice_mode"]=np.where(e.practice_loss_kWh_t.eq(cfg["practice_modes"]["normal"]["practice_loss"]),"normal","practice_loss_40")
    e.to_parquet(preds/"test_heat_predictions.parquet",index=False)
    load_pred=pd.read_parquet(MODELS/"load/test_predictions.parquet").rename(columns={q:f"load_{q}_kW" for q in ("p10","p50","p90")})
    load_pred["interval_start"]=load_pred.target_start;load_pred["interval_end"]=load_pred.target_end
    load_pred["available_at"]=load_pred.forecast_origin;load_pred["component"]="AUX"
    load_pred.to_parquet(preds/"test_load_predictions.parquet",index=False)
    health_pred=pd.concat([pd.read_parquet(MODELS/f"health/{a}/test_predictions.parquet") for a in cfg["health_assets"]],ignore_index=True)
    health_pred["horizon_hours"]=par["health_horizon_hours"];health_pred["available_at"]=health_pred.forecast_origin
    health_pred.to_parquet(preds/"test_health_predictions.parquet",index=False)
    contract=dict(version=cfg["version"],timezone="Asia/Kolkata",interval_minutes=15,
                  candidate_liquid_t=values(yaml.safe_load((ROOT/"data/processed/sim_v1.1/config_snapshot.yaml").read_text()))["if"]["liquid_per_heat"],
                  practice_modes={k:dict(practice_loss_kWh_t=v["practice_loss"]) for k,v in cfg["practice_modes"].items()},
                  load_components=["AUX"],load_max_horizon_slots=par["load_horizon_slots"],load_origin="local midnight",
                  excluded_scheduled_components=["IF_01","MILL_01","RHF_01","PMP_01","CMP_01"],
                  health_assets=cfg["health_assets"],health_horizon_hours=par["health_horizon_hours"],
                  interpretation="p10/p50/p90 individual-outcome empirical prediction quantiles; p90 is NOT a hard physical bound",
                  input_envelope="features (exact ordered artifact schema), available_at per field, forecast_origin; all publications <= origin",
                  fallback="Training-only empirical baseline if production artifact missing, explicitly unusable for constraints; absent metadata fails closed.")
    write_json(MODELS/"prediction_contract.json",contract)
    write_json(MODELS/"training_summary.json",results)
    # Attach precise training provenance to each independent model artifact.
    for name,result in results.items():
        folder=MODELS/("health/"+name.removeprefix("health_") if name.startswith("health_") else "external/"+name if name in ("uci","ai4i") else name)
        source=CORPUS/("external/"+name if name in ("uci","ai4i") else "datasets/"+name)
        result["training_data_version"]="training_v1" if name not in ("uci","ai4i") else name+"_frozen_clean_v1"
        result["data_hashes"]={p.name:sha256(p) for p in sorted(source.glob('*.parquet'))}
        result["split_manifest"]="data/processed/training_v1/split_manifest.json" if name not in ("uci","ai4i") else "data/interim/"+name.replace("uci","uci_steel")+"_split_manifest.parquet"
        write_json(folder/"metadata.json",result)
    write_json(MODELS/"training_summary.json",results)
    write_json(MODELS/"runtime_manifest.json",dict(python=platform.python_version(),dependencies={p:importlib.metadata.version(p) for p in ("numpy","pandas","pyarrow","scikit-learn","lightgbm","scipy","joblib","PyYAML")},
                                               requirements_sha256=sha256(ROOT/"requirements-phase2b.lock.txt"),threads=1))
    (MODELS/"config_snapshot.yaml").write_bytes((ROOT/"configs/forecast_v1.yaml").read_bytes())
    from energy_copilot.forecast.reporting import report
    report(results,manifest,cfg,CORPUS,MODELS)
    write_json(MODELS/"protected_inputs_check.json",protected())
    write_json(MODELS/"artifact_manifest.json",{str(p.relative_to(MODELS)).replace('\\','/'):sha256(p) for p in sorted(MODELS.rglob('*')) if p.is_file() and p.name!="artifact_manifest.json"})


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--corpus-only",action="store_true");parser.add_argument("--audit-only",action="store_true")
    args=parser.parse_args();setup();raw=yaml.safe_load((ROOT/"configs/forecast_v1.yaml").read_text());validate_parameters(raw);cfg=values(raw)
    print(preflight(),flush=True)
    if args.audit_only:return
    manifest=build_corpus(cfg)
    if not args.corpus_only:
        warnings.filterwarnings("ignore",message="X does not have valid feature names")
        train(cfg,manifest)


if __name__=="__main__":main()
