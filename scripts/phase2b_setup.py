"""Create Phase-II-B-only configuration and a protection snapshot; never rewrite old files."""
from pathlib import Path
import yaml
from energy_copilot.common import ROOT, parameter, write_json, sha256


def setup():
    file=ROOT/"configs/forecast_v1.yaml"
    if not file.exists():
        cfg=dict(version="forecast_v1",source_version="sim_v1.1",analytics_version="analytics_v1",
                 background_components=["AUX"],health_assets=["MILL_01","PMP_01"])
        params=dict(seed=42,days=30,load_horizon_slots=96,health_horizon_hours=24,health_stride_slots=4,
                    load_lags=[1,2,4,96],load_windows=[4,96],ridge_alpha=10.,logistic_C=1.,calibrator_C=100.,max_iter=2000,
                    trees=220,leaves=15,learning_rate=.05,min_child_samples=40,reg_lambda=2.,
                    minimum_improvement=.02,health_minimum_pr_gain=.01,min_calibration_group=30,
                    threshold_grid=[.05,.1,.15,.2,.25,.3,.35,.4,.45,.5,.55,.6,.65,.7,.75,.8,.85,.9,.95])
        cfg["parameters"]={k:parameter(v,"h" if k=="health_horizon_hours" else "day" if k=="days" else "15-minute slot" if k in ("load_horizon_slots","health_stride_slots") else "training setting",
                           "assumption","Phase II-B declared experimental design", "Model-only setting; does not change frozen physical config. Threshold and model selection use validation only.") for k,v in params.items()}
        cfg["seeds"]={s:parameter(v,"simulation seed","assumption","Whole-seed four-way partition fixed before training","All practice variants and failure episodes of each seed remain together.") for s,v in
                      dict(train=list(range(101,115)),validation=list(range(115,119)),calibration=list(range(119,122)),test=list(range(122,126))).items()}
        cfg["practice_modes"]={"normal":dict(practice_loss=parameter(60.,"kWh/t liquid","sourced","sim_v1.1/config_snapshot.yaml if.practice_loss","Unchanged baseline decision.")),
                               "practice_loss_40":dict(practice_loss=parameter(40.,"kWh/t liquid","assumption","Unchanged simulate(practice={'practice_loss': ...}) interface","Explicit illustrative process decision, not a measured or best-safe practice claim; faults are never suppressed. Energy and powered time follow unchanged physics."))}
        file.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
    snapshot=ROOT/"configs/phase2b_readonly_manifest.json"
    if not snapshot.exists():
        paths=[]
        for root in ("data/raw","data/interim","data/processed/sim_v1.0","data/processed/sim_v1.1","data/processed/analytics_v1","Readme","src/energy_copilot/sim","src/energy_copilot/analytics"):
            paths += [p for p in (ROOT/root).rglob('*') if p.is_file() and "__pycache__" not in p.parts]
        paths += [ROOT/p for p in ("configs/plant_v1.yaml","configs/calibration_v1.yaml","configs/schema.yaml","configs/analytics_v1.yaml","requirements.txt","requirements.lock.txt","src/energy_copilot/common.py","src/energy_copilot/schema.py")]
        write_json(snapshot,{str(p.relative_to(ROOT)).replace('\\','/'):sha256(p) for p in sorted(set(paths))})
    lock=ROOT/"requirements-phase2b.lock.txt"
    if not lock.exists():lock.write_text((ROOT/"requirements.lock.txt").read_text()+"lightgbm==4.6.0\n",encoding="utf-8")


if __name__=="__main__":setup()

