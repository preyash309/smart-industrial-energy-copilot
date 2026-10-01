"""Versioned robust scheduling experiment. Final seeds require a frozen design."""
from pathlib import Path
from dataclasses import replace,asdict
import argparse,json
import numpy as np
import pandas as pd
from energy_copilot.common import load_config,values,write_json,canonical_hash,sha256
from energy_copilot.forecast import PredictionService
from energy_copilot.sim import simulate as original_simulate
from energy_copilot.replay.compatible_v111 import simulate
from energy_copilot.replay.runner import replay_case
from energy_copilot.replay.adapter import ReplayControls
from energy_copilot.replay.scenarios import scenario_proof
from energy_copilot.replay.history import seed_input
from energy_copilot.optimization import optimize
from energy_copilot.optimization.contracts import input_from_dict
from energy_copilot.robust.integrity import protect_upstream,verify_upstream,validate_split,require_development,freeze_policy
from energy_copilot.robust import ReservePolicy,optimize_robust
from energy_copilot.robust.scenarios import make_scenarios
from energy_copilot.robust.receding_horizon import run_adaptive
from energy_copilot.robust.evaluation import evaluate_plan,evaluate_adaptive,compare_all
from energy_copilot.robust.state_update import public_snapshot,update_state,remaining_input

OUTPUT_OVERRIDE=None


def settings():
    c=values(load_config('configs/robustness_v1.yaml'));split=json.loads(Path(c['split_manifest']).read_text());validate_split(split)
    out=Path(OUTPUT_OVERRIDE or c['output_directory'])
    protected_roots=['data/raw','data/processed/sim_v1.0','data/processed/sim_v1.1','data/processed/analytics_v1','models/phase2b_v1','plans/optimizer_v1','replay/optimizer_v1']
    if any(out.resolve()==Path(p).resolve() or Path(p).resolve() in out.resolve().parents for p in protected_roots):raise ValueError('Output path lies within frozen upstream evidence')
    if (out/'release_manifest.json').exists():raise RuntimeError('Released robustness output is immutable; reproduce with --output in a new directory')
    out.mkdir(parents=True,exist_ok=True)
    return c,split,out,load_config(c['plant_config']),PredictionService(c['prediction_directory'])


def template_input():return input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))


def seed_context(seed,c,cfg,service):
    baseline=original_simulate(cfg,seed=seed,days=c['horizon_days'])
    inp,_=seed_input(template_input(),baseline.readings,baseline.heats,baseline.production,values(cfg),service)
    return baseline,inp


def calibrate():
    protection=protect_upstream();c,split,out,cfg,service=settings();rows=[];vectors=[]
    for seed in split['development']:
        require_development(seed,split);baseline,inp=seed_context(seed,c,cfg,service)
        ref=simulate(cfg,seed=seed,days=c['horizon_days'],practice_by_day={7:40})
        h=ref.heats[ref.heats.start.ge(pd.Timestamp(c['origin']))&ref.heats.start.lt(pd.Timestamp(c['origin'])+pd.Timedelta(days=1))].sort_values('start')
        vector=[]
        for r in h.itertuples():
            p=next(k.prediction for k in inp.heat_candidates if k.heat_id==r.heat_id and k.prediction.practice_mode==c['practice'] and pd.Timestamp(k.start).hour==r.start.hour)
            duration=float((r.end-r.start).total_seconds()/60);residual=duration-p.duration_p50_min;vector.append(residual)
            rows.append(dict(seed=seed,heat_id=r.heat_id,actual_duration_min=duration,p50=p.duration_p50_min,p90=p.duration_p90_min,residual_min=residual,available_at=r.end))
        vectors.append(vector);print('development calibration',seed,flush=True)
    x=np.asarray(vectors);positive=np.maximum(0,x.ravel());order=np.argsort(x.sum(axis=1));chosen=[vectors[int(order[len(order)//2])],vectors[int(order[-1])]]
    a=x[:,:-1].ravel();b=x[:,1:].ravel();lag=float(np.corrcoef(a,b)[0,1])
    calibration=dict(version='duration_scenarios_v1',source_seeds=split['development'],source_day=7,practice=c['practice'],target='public completed duration minus frozen midnight p50',
                     positive_residual_p95_min=float(np.quantile(positive,.95)),selected_day_residual_vectors=chosen,all_day_vectors=vectors,
                     pooled_adjacent_heat_residual_correlation=lag,day_mean_residuals=x.mean(axis=1).tolist(),
                     correlation_limit='Six complete days only; correlation estimate is diagnostic. Whole-day vectors retain observed dependence without an independence assumption.',
                     generation_rule='central, marginal p90, median/high-total complete development vectors, one severe next heat; hard shared-start/shared-rolling feasibility')
    pd.DataFrame(rows).to_parquet(out/'development_duration_residuals.parquet',index=False)
    write_json(out/'duration_calibration.json',calibration);write_json(out/'split_manifest.json',split);write_json(out/'upstream_integrity.json',protection)
    verify_upstream()


def develop(seed_only=None):
    c,split,out,cfg,service=settings();cal=json.loads((out/'duration_calibration.json').read_text());trials=[]
    for seed in split['development']:
        if seed_only is not None and seed!=seed_only:continue
        require_development(seed,split);baseline,inp=seed_context(seed,c,cfg,service)
        state=update_state(None,inp.forecast_origin,public_snapshot(baseline,inp.forecast_origin)[1],[],[],inp)
        planning,_=remaining_input(inp,state,public_snapshot(baseline,inp.forecast_origin),values(cfg),service,grid=c['start_grid_minutes'])
        for reserve in c['reserve_candidates']:
            for fraction in c['buffer_fraction_candidates']:
                directory=out/f'development_grid{c["start_grid_minutes"]}'/f'seed_{seed}'/f'reserve_{reserve}_buffer_{fraction}'
                if (directory/'replay_results.json').exists():
                    entry=json.loads((directory/'replay_results.json').read_text())
                else:
                    policy=ReservePolicy(reserve,fraction);plan=optimize_robust(planning,policy,make_scenarios(cal,[h.heat_id for h in planning.heats]))
                    write_json(directory/'robust_plan.json',plan.to_dict())
                    entry=evaluate_plan('development_static_robust',baseline,planning,plan.plan,seed,c['horizon_days'],directory)
                trials.append(dict(seed=seed,reserve_min=reserve,buffer_fraction=fraction,result=entry));print('development policy',seed,reserve,fraction,entry['status'],flush=True)
    if seed_only is not None:
        write_json(out/f'development_trials_grid{c["start_grid_minutes"]}_seed{seed_only}.json',trials)
        return
    summary=[]
    for reserve in c['reserve_candidates']:
        for fraction in c['buffer_fraction_candidates']:
            subset=[r for r in trials if r['reserve_min']==reserve and r['buffer_fraction']==fraction];valid=[r for r in subset if r['result']['status']=='physically_valid']
            summary.append(dict(reserve_min=reserve,buffer_fraction=fraction,attempted=len(subset),feasible=len(valid),feasibility_rate=len(valid)/len(subset),conditional_cost_Rs=None if not valid else float(np.mean([r['result']['realized_metrics']['physical_evaluation_tariff_cost_Rs'] for r in valid]))))
    # Declared lexicographic selection: success count, then conditional cost,
    # then smaller reserve/buffer. Failed scenarios remain in the denominator.
    best=min(summary,key=lambda x:(-x['feasible'],float('inf') if x['conditional_cost_Rs'] is None else x['conditional_cost_Rs'],x['reserve_min'],x['buffer_fraction']))
    # Smallest positive reserve with equal development success and within the
    # predeclared cost budget; do not simply maximize reserve.
    if best['conditional_cost_Rs'] is not None:
        eligible=[x for x in summary if x['feasible']==best['feasible'] and x['reserve_min']>0 and x['conditional_cost_Rs'] is not None and x['conditional_cost_Rs']<=best['conditional_cost_Rs']*(1+c['reserve_cost_budget_fraction'])]
        if eligible:best=min(eligible,key=lambda x:(x['reserve_min'],x['conditional_cost_Rs'],x['buffer_fraction']))
    node=freeze_policy(out/'design_freeze.json',dict(end_margin_min=best['reserve_min'],uncertainty_buffer_fraction=best['buffer_fraction'],minimum_buffer_min=0.0),cal,split)
    write_json(out/f'development_policy_comparison_grid{c["start_grid_minutes"]}.json',summary);write_json(out/f'development_trials_grid{c["start_grid_minutes"]}.json',trials);verify_upstream()
    print('design frozen',node['policy'],flush=True)


def evaluate(partition,seed_only=None):
    c,split,out,cfg,service=settings();freeze=json.loads((out/'design_freeze.json').read_text());cal=json.loads((out/'duration_calibration.json').read_text())
    original_hash=freeze.pop('design_sha256')
    if canonical_hash(freeze)!=original_hash or freeze['calibration_sha256']!=canonical_hash(cal) or freeze['split_sha256']!=canonical_hash(split):raise ValueError('Design freeze mismatch')
    if freeze['config_sha256']!=sha256('configs/robustness_v1.yaml') or any(sha256(p)!=d for p,d in freeze['source_hashes'].items()):raise ValueError('Policy/runtime changed after design freeze')
    if partition=='final_regression' and not (out/'validation_comparison.json').exists():raise ValueError('Validation gate must precede frozen final regression')
    policy=ReservePolicy(**freeze['policy']);rows=[]
    seeds=split[partition]
    if seed_only is not None:
        if seed_only not in seeds:raise ValueError('Seed does not belong to requested split')
        seeds=[seed_only]
    for seed in seeds:
        baseline,inp=seed_context(seed,c,cfg,service)
        root=out/partition/f'seed_{seed}'
        reference_path=root/'reference_same_practice.json'
        if not reference_path.exists():
            controls=ReplayControls({}, {7:40}, {}, 'Matched reference back-to-back and rolling, same synthetic practice as all strategies',inp.forecast_origin,(pd.Timestamp(inp.forecast_origin)+pd.Timedelta(days=1)).isoformat())
            ref,_=replay_case('reference_same_practice',baseline,inp,controls,seed,c['horizon_days'],scenario_proof(cfg,seed,c['horizon_days']))
            write_json(reference_path,ref)
        for strategy in ('E0','E1','E2','E3','E4'):
            folder=root/strategy
            if (folder/'replay_results.json').exists():
                entry=json.loads((folder/'replay_results.json').read_text())
            elif strategy in ('E0','E1'):
                current=replace(inp,optimization_mode='conservative' if strategy=='E1' else 'central')
                plan=optimize(current);entry=evaluate_plan(strategy,baseline,current,plan,seed,c['horizon_days'],folder)
            elif strategy=='E2':
                state=update_state(None,inp.forecast_origin,public_snapshot(baseline,inp.forecast_origin)[1],[],[],inp)
                planning,_=remaining_input(inp,state,public_snapshot(baseline,inp.forecast_origin),values(cfg),service,grid=c['start_grid_minutes'])
                plan=optimize_robust(planning,policy,make_scenarios(cal,[h.heat_id for h in inp.heats]));write_json(folder/'robust_plan.json',plan.to_dict())
                entry=evaluate_plan(strategy,baseline,planning,plan.plan,seed,c['horizon_days'],folder)
            else:
                ctrl,controls=run_adaptive(inp,cfg,seed,c['horizon_days'],service,ReservePolicy() if strategy=='E3' else policy,cal,folder,robust=strategy=='E4',grid=c['start_grid_minutes'])
                entry=evaluate_adaptive(strategy,baseline,inp,ctrl,controls,seed,c['horizon_days'],folder)
            if strategy in ('E3','E4'):
                count=len(list(folder.glob('replan_step_*.json')))
                if entry.get('replans')!=count:entry=dict(entry,original_reported_replans=entry.get('replans'),replans=count,replan_count_source='independent count of retained step files')
            rows.append(dict(seed=seed,strategy=strategy,result=entry))
            print(partition,seed,strategy,entry['status'],entry.get('reason',entry.get('violation','')),flush=True)
        if partition=='final_regression':
            previous=json.loads((Path('replay/optimizer_v1/evaluation')/f'seed_{seed}'/'case_results.json').read_text())
            regression={}
            for strategy,key in [('E0','S3'),('E1','conservative_synthetic')]:
                entry=next(r['result'] for r in rows if r['seed']==seed and r['strategy']==strategy)
                regression[key]=dict(status_match=entry['status']==previous[key]['status'],metrics_match=entry.get('realized_metrics')==previous[key].get('realized_metrics'))
            for key,name in [('S1','c3_tariff_normal'),('conservative_normal','conservative_tariff_normal')]:
                from energy_copilot.optimization.contracts import OptimizerResult
                p=Path('replay/optimizer_v1/evaluation')/f'seed_{seed}'/'optimized'/name/'optimizer_result.json'
                original=OptimizerResult(**json.loads(p.read_text()));current=replace(inp,optimization_mode=original.optimization_mode)
                fresh=evaluate_plan('D_reproduction_'+key,baseline,current,original,seed,c['horizon_days'],root/'D_reproduction'/key)
                regression[key]=dict(status_match=fresh['status']==previous[key]['status'],metrics_match=fresh.get('realized_metrics')==previous[key].get('realized_metrics'))
            if not all(all(v.values()) for v in regression.values()):raise RuntimeError('E0 / frozen Phase II-D regression mismatch')
            write_json(root/'E0_regression.json',regression)
        write_json(root/'attempt_results.json',[r for r in rows if r['seed']==seed])
    if seed_only is not None:return
    verify_upstream();write_json(out/f'{partition}_results.json',rows)
    compare=compare_all(rows);write_json(out/f'{partition}_comparison.json',compare)
    failures=[dict(seed=r['seed'],strategy=r['strategy'],status=r['result']['status'],cause=r['result'].get('failure_class'),reason=r['result'].get('reason',r['result'].get('violation')),retained=True) for r in rows if r['result']['status']!='physically_valid']
    pd.DataFrame(failures).to_parquet(out/f'{partition}_failure_analysis.parquet',index=False)
    if partition=='final_regression':write_json(out/'robustness_comparison.json',compare)


def main():
    global OUTPUT_OVERRIDE
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['calibrate','develop','development_evaluate','validate','final']);ap.add_argument('--seed',type=int);ap.add_argument('--output');a=ap.parse_args();OUTPUT_OVERRIDE=a.output
    if a.stage=='calibrate':calibrate()
    elif a.stage=='develop':develop(a.seed)
    else:evaluate('development' if a.stage=='development_evaluate' else 'validation' if a.stage=='validate' else 'final_regression',a.seed)


if __name__=='__main__':main()
