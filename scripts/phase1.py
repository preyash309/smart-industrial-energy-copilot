"""Rebuild Phase I, gate by gate. Never overwrite a changed frozen version."""
from __future__ import annotations
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "src"))

from energy_copilot.common import load_config, values, sha256, write_json
from energy_copilot.data.prepare import main as prepare
from energy_copilot.schema import create_schema, validate_table
from energy_copilot.sim import simulate
from scripts.create_config import create
from scripts.report import compare_temporal, report, assumption_register, runtime_manifest


def gate(paths, log):
    command=[sys.executable,"-m","pytest",*paths,"-q"]
    completed=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
    print(completed.stdout,flush=True)
    if completed.returncode:
        print(completed.stderr,file=sys.stderr)
        raise RuntimeError(f"Validation stopped at {paths}")
    log.append(dict(stage=paths,result="PASS",output=completed.stdout.strip()))


def write_data_card(result, target):
    s=result.summary
    card=f"""# sim_v1.0 data card

**Simulated reference plant; Phase-I feasibility dataset.** Seed {s['seed']}, 2026-01-05 through 2026-02-03 local Indian calendar, 30 days, {s['working_days']} working days, {s['heats']} heats. Six consuming branches and MAIN incomer, 15-minute interval starts; {len(result.readings):,} observed rows. Public real datasets are separate: UCI Steel is Korean industrial energy; AI4I is synthetic snapshots. No row-wise merging and no model training.

Inputs: supplied Reference Plant Spec v2, Data Workflow, roadmap and simple workflow; UCI Jan-Aug training-only normalized AUX profile; all technical assumptions have metadata in config_snapshot.yaml. Plant scale comes from the spec, not UCI. Calibration, schema, source hashes, dependency lock, source-code hashes, runtime, seed and validation are snapshotted beside these tables.

readings.parquet contains observed meter/sensor channels with independent noise, gaps and glitches. heats.parquet contains operator register fields, noisy heat energy and tap-temperature measurements plus curated fault labels (targets only). production.parquet is an exact synthetic per-shift mass register. events.parquet contains ground-truth labels for supervision/evaluation and is not a feature input.

latent_truth.parquet and latent_heats.parquet are **internal only**: physical balances, wear and energy components. The loader only allows observed readings features. Never expose latent wear, health, true severity, future failure timestamps, fault labels or future outcomes to predictors. Keep failure cycles together and use time splits in any later simulated ML work; no such work is performed here.

Hard acceptance gates and byte-identical same-seed replay pass. IF SEC {s['mean_if_sec_kWh_t']:.3f} kWh/t, electricity {s['mean_working_day_MWh']:.3f} MWh/working day, IF share {s['if_working_day_share']:.2%}, peak demand {s['peak_kVA']:.2f} kVA. Full validation_report.md documents lag-4 divergence from UCI; temporal diagnostics are not fitted identity constraints. Do not treat this as field validation or a basis for savings claims.

Limits: reduced-order caster/RHF control; detailed chemistry unmodelled; pressure/flow, melt yield and repairs assumed; accelerated calendar-age degradation about two weeks, not validated annual reliability; synthetic weather; Sundays off with background loads. No Phase-II models, optimisation, dashboard, synthetic generative models, emissions/savings totals or payback claims.

Version immutable: any changed content requires a new version directory. Rebuild with `python -m scripts.phase1` under Python 3.12 and requirements.lock.txt; it runs all validation gates and compares this folder before accepting an existing freeze.
"""
    (target / "data_card.md").write_text(card,encoding="utf-8")


def freeze(result,comparison,repro,log):
    candidate=ROOT / "data/runs/freeze_candidate"
    candidate.mkdir(parents=True,exist_ok=True)
    result.write(candidate)
    for original,name in [("configs/schema.yaml","schema.yaml"),("configs/calibration_v1.yaml","calibration_v1.yaml"),
                          ("requirements.lock.txt","requirements.lock.txt"),("data/raw/source_hashes.json","source_hashes.json"),
                          ("reports/sim_report_card.md","validation_report.md"),("reports/validation_report.json","validation_report.json"),
                          ("reports/assumption_register.md","assumption_register.md"),("reports/temporal_validation.json","temporal_validation.json")]:
        shutil.copyfile(ROOT / original,candidate / name)
    write_json(candidate / "seed.json",dict(seed=result.scenario_manifest["seed"]))
    write_json(candidate / "runtime_manifest.json",runtime_manifest())
    sources=[*sorted((ROOT / "src").rglob("*.py")),*sorted((ROOT / "scripts").rglob("*.py")),*sorted((ROOT / "tests").rglob("*.py")),ROOT / "pyproject.toml",ROOT / "requirements.txt"]
    write_json(candidate / "code_manifest.json",{str(p.relative_to(ROOT)).replace("\\","/"):sha256(p) for p in sources})
    write_data_card(result,candidate)
    hashes={p.name:sha256(p) for p in sorted(candidate.iterdir()) if p.is_file() and p.name!="freeze_manifest.json"}
    write_json(candidate / "freeze_manifest.json",dict(version="sim_v1.0",hashes=hashes))
    target=ROOT / "data/processed/sim_v1.0"
    if target.exists():
        prior=json.loads((target / "freeze_manifest.json").read_text())
        if prior["hashes"]!=hashes:
            raise RuntimeError("Frozen sim_v1.0 content changed; choose a new dataset version, never overwrite")
        for name,digest in hashes.items():
            if sha256(target / name)!=digest:
                raise RuntimeError(f"Frozen file modified: {name}")
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(candidate,target)
    write_json(ROOT / "reports/gate_log.json",dict(gates=log,frozen_path="data/processed/sim_v1.0",reproducibility=repro))
    print(f"Phase-I frozen: {target}",flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--init-config",action="store_true",help="Create initial plant parameter transcription if missing")
    args=parser.parse_args()
    if not (ROOT / "configs/plant_v1.yaml").exists():
        if not args.init_config:
            parser.error("plant_v1.yaml missing; use --init-config")
        create()
    for name in ("data/interim","data/processed","reports/figures","notebooks"):
        (ROOT / name).mkdir(parents=True,exist_ok=True)
    installed=runtime_manifest()["dependencies"]
    for line in (ROOT / "requirements.lock.txt").read_text().splitlines():
        if "==" in line:
            name,version=line.split("==")
            if installed[name]!=version:
                raise RuntimeError(f"Unpinned runtime: {name} {installed[name]} != {version}")
    log=[]
    prepare();assumption_register();create_schema()
    gate(["tests/test_data.py","tests/test_v0.py"],log)
    config=load_config();v0=load_config();v0["stochastic"]=False
    v0["observations"]["relative_noise"]["value"]=0;v0["observations"]["sensor_noise"]["value"]=0
    deterministic=simulate(v0,days=2,seed=values(config)["seed"])
    deterministic.write(ROOT / "data/runs/v0_48h");write_json(ROOT / "reports/v0_gate.json",deterministic.summary)
    gate(["tests/test_v1.py"],log)
    gate(["tests/test_acceptance.py"],log)
    seed=values(config)["seed"]
    result=simulate(config,seed=seed,days=30);again=simulate(config,seed=seed,days=30)
    first=ROOT / "data/runs/v1_30d";second=ROOT / "data/runs/replay"
    result.write(first);again.write(second)
    equal={name:sha256(first / f"{name}.parquet")==sha256(second / f"{name}.parquet") for name in ("readings","heats","production","events","latent_truth","latent_heats")}
    if not all(equal.values()):
        raise RuntimeError("Same-seed byte reproducibility gate failed")
    for table in create_schema()["tables"]:
        validate_table(getattr(result,table),table)
    comparison=compare_temporal(result)
    report(result,comparison,equal)
    freeze(result,comparison,equal,log)


if __name__=="__main__":
    main()
