"""Matched-condition replay. Never overwrite a released upstream or replay artifact."""
from pathlib import Path
from dataclasses import replace,asdict
import argparse
import json
import platform
import shutil
import numpy as np
import pandas as pd
import yaml
from energy_copilot.common import load_config,values,sha256,write_json,canonical_hash
from energy_copilot.sim import simulate as frozen_simulate
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization import optimize
from energy_copilot.optimization.contracts import input_from_dict,OptimizerResult
from energy_copilot.replay.compatible_v111 import simulate
from energy_copilot.replay.adapter import ReplayControls,adapt_plan
from energy_copilot.replay.runner import replay_case
from energy_copilot.replay.scenarios import scenario_proof
from energy_copilot.replay.origin_state import TABLES,frame_hash
from energy_copilot.replay.history import seed_input
from energy_copilot.replay.attribution import attribution,robustness

PLAN_NAMES={'S1':'c3_tariff_normal','S3':'c4_tariff_synthetic',
            'conservative_normal':'conservative_tariff_normal','conservative_synthetic':'conservative_tariff_synthetic'}


def protected():
    h=json.loads(Path('configs/phase2d_readonly_manifest.json').read_text())
    changed=[p for p,d in h.items() if not Path(p).is_file() or sha256(p)!=d]
    if changed:raise RuntimeError('Frozen upstream hash change: '+str(changed))
    return dict(status='PASS',protected_files=len(h))


def reference_results():
    return {key:OptimizerResult(**json.loads((Path('plans/optimizer_v1')/name/'result.json').read_text())) for key,name in PLAN_NAMES.items()}


def evaluate_seed(seed, inp, plans, cfg, days, out, practice_loss):
    baseline=frozen_simulate(cfg,seed=seed,days=days)
    proof=scenario_proof(cfg,seed,days);cases={};origin=inp.forecast_origin
    end=(pd.Timestamp(origin)+pd.Timedelta(days=1)).isoformat();day=(pd.Timestamp(origin)-pd.Timestamp(values(cfg)['start'])).days
    write_json(out/'scenario_proof.json',proof);write_json(out/'optimizer_input.json',asdict(inp))
    control=ReplayControls({}, {}, {},'conventional reference policy; no tariff decision',origin,end)
    cases['S0'],_=replay_case('S0',baseline,inp,control,seed,days,proof,out/'baseline')
    if cases['S0']['status']!='physically_valid':raise RuntimeError('Baseline failed; retain evidence and stop, no alternate seed')
    # Practice-only uses unchanged reference policies; earlier history remains normal.
    control=ReplayControls({}, {day:practice_loss}, {},'SYNTHETIC-PRACTICE only; reference back-to-back/rolling policies',origin,end)
    cases['S2'],_=replay_case('S2',baseline,inp,control,seed,days,proof,out/'practice_only')
    for key,result in plans.items():
        current=replace(inp,optimization_mode=result.optimization_mode,objective_mode=result.objective_mode)
        directory=out/'optimized'/PLAN_NAMES[key]
        if not result.releasable:
            cases[key]=dict(case=key,status='optimizer_infeasible',retained=True,reason=result.reason,realized_metrics=None)
            write_json(directory/'failure.json',cases[key]);continue
        try:control=adapt_plan(current,result,cfg)
        except ValueError as exc:
            cases[key]=dict(case=key,status='unsupported',reason=str(exc),realized_metrics=None,retained=True)
            write_json(directory/'failure.json',cases[key]);continue
        cases[key],_=replay_case(key,baseline,current,control,seed,days,proof,directory,result)
        print(seed,key,cases[key]['status'],cases[key].get('violation',''),flush=True)
    write_json(out/'paired_comparison.json',attribution(cases));write_json(out/'case_results.json',cases)
    return cases,baseline


def run(output=None,primary_only=False):
    protection=protected();raw=load_config('configs/replay_v1.yaml');r=values(raw)
    out=Path(output or r['output_directory'])
    if (out/'release_manifest.json').exists():raise RuntimeError('Replay artifact released; use a new --output directory')
    out.mkdir(parents=True,exist_ok=True);cfg=load_config(r['plant_config']);days=r['horizon_days']
    inp=input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))
    assert inp.forecast_origin==r['origin'];seed=r['primary_seed']
    plans=reference_results();primary,baseline=evaluate_seed(seed,inp,plans,cfg,days,out/'primary',r['practice_loss_40'])
    # Full default regression against BOTH frozen engine and historical frozen files.
    default=simulate(cfg,seed=seed,days=days)
    regression={name:getattr(default,name).equals(getattr(baseline,name)) for name in TABLES}
    regression['summary']=default.summary==baseline.summary;regression['manifest']=default.scenario_manifest==baseline.scenario_manifest
    regression['historical_artifact']={name:getattr(default,name).equals(pd.read_parquet(Path('data/processed/sim_v1.1')/(name+'.parquet'))) for name in TABLES}
    if not all(regression[k] for k in (*TABLES,'summary','manifest')) or not all(regression['historical_artifact'].values()):
        raise RuntimeError('Replay layer changed default V1.1 outputs')
    write_json(out/'default_regression.json',regression)
    # Repeat accepted original plan; exact numerical and Parquet-byte output checks.
    control=adapt_plan(replace(inp,objective_mode='cost'),plans['S1'],cfg)
    repeat=simulate(cfg,schedule=control.schedule,seed=seed,days=days,practice_by_day=control.practice_by_day,rolling_dispatch=control.rolling_dispatch)
    first=out/'primary/optimized/c3_tariff_normal/simulation'
    replay_repro={name:frame_hash(getattr(repeat,name))==sha256(first/(name+'.parquet')) for name in TABLES}
    if not all(replay_repro.values()):raise RuntimeError('Replay reproducibility failure')
    write_json(out/'reproducibility.json',dict(status='PASS',seed=seed,same_plan_byte_identical=replay_repro))
    allruns={};service=PredictionService('models/phase2b_v1')
    selected=[] if primary_only else r['evaluation_seeds']
    if set(selected)&set(range(101,126)):raise RuntimeError('Evaluation seed overlaps Phase-II-B corpus')
    for s in selected:
        common=frozen_simulate(cfg,seed=s,days=days)
        current,provenance=seed_input(inp,common.readings,common.heats,common.production,values(cfg),service)
        folder=out/'evaluation'/f'seed_{s}'
        write_json(folder/'past_only_origin_provenance.json',provenance)
        candidates={}
        for key in PLAN_NAMES:
            mode='conservative' if key.startswith('conservative') else 'central'
            current_mode=replace(current,optimization_mode=mode)
            practices=('normal',) if key in ('S1','conservative_normal') else None
            candidates[key]=optimize(current_mode,practices=practices)
            write_json(folder/'predicted_plans'/f'{key}.json',candidates[key].to_dict())
        allruns[str(s)],_=evaluate_seed(s,current,candidates,cfg,days,folder,r['practice_loss_40'])
        # Layer defaults also match frozen engine for every additional seed.
        copied=simulate(cfg,seed=s,days=days)
        eq={name:frame_hash(getattr(common,name))==frame_hash(getattr(copied,name)) for name in TABLES}
        if not all(eq.values()):raise RuntimeError('Additional-seed default regression failed')
        write_json(folder/'default_regression.json',eq)
    write_json(out/'robustness.json',robustness(allruns) if allruns else dict(status='pending'))
    write_json(out/'evaluation_split_manifest.json',dict(primary_seed=seed,evaluation_seeds=selected,excluded_phase2b_seeds=list(range(101,126)),
        predeclared_config_sha256=sha256('configs/replay_v1.yaml'),no_cherry_picking=True,seed_specific_past_only_predictions=True))
    failures=[]
    for s,cases in [(str(seed),primary),*allruns.items()]:
        for key,entry in cases.items():
            if entry['status']!='physically_valid':failures.append(dict(seed=int(s),case=key,status=entry['status'],category=entry.get('category','unsupported simulator control'),reason=entry.get('violation',entry.get('reason','')),retained=True))
            elif 'forecast_errors' in entry:
                for task in ('heat_energy','heat_duration','AUX_physical'):
                    err=entry['forecast_errors'][task]
                    failures.append(dict(seed=int(s),case=key,status='diagnostic',category=task+' forecast miss',reason=json.dumps(err,sort_keys=True),retained=True))
    pd.DataFrame(failures).to_parquet(out/'failure_analysis.parquet',index=False)
    manifest=dict(version='replay_v1',layer=r['layer'],origin=r['origin'],end=r['end'],protected=protected(),
        complete_decision_loop=any(e['status']=='physically_valid' for key,e in primary.items() if key in PLAN_NAMES),
        primary=primary,evaluation_seeds=selected,primary_attribution=attribution(primary),robustness=robustness(allruns) if allruns else {},
        multi_seed_status='completed' if len(selected)>=10 else 'pending',tests='pending',recalibration=False,reoptimization=False,field_savings=False)
    write_json(out/'experiment.json',manifest)
    for src in ('configs/replay_v1.yaml','configs/replay_compatibility_manifest.json','requirements-phase2c.lock.txt'):
        shutil.copyfile(src,out/Path(src).name)
    from scripts.phase2d_release import reports
    reports(out,manifest)
    print('Evaluation complete; physically invalid original plans retained. Protected',protection['protected_files'],'files.',flush=True)
    return manifest


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output');ap.add_argument('--primary-only',action='store_true');args=ap.parse_args()
    run(args.output,args.primary_only)

