"""Phase II-F synthetic maintenance experiment. Final seeds require a frozen design."""
from dataclasses import asdict,replace
from pathlib import Path
import argparse,json
import pandas as pd
from energy_copilot.common import load_config,values,write_json,sha256,canonical_hash
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization.contracts import input_from_dict
from energy_copilot.replay.history import seed_input
from energy_copilot.replay.adapter import ReplayControls
from energy_copilot.sim import simulate as baseline_simulate
from energy_copilot.robust import ReservePolicy
from energy_copilot.robust.receding_horizon import run_adaptive
from energy_copilot.robust.evaluation import evaluate_adaptive
from energy_copilot.maintenance.policy import MaintenancePolicy
from energy_copilot.maintenance.contracts import MaintenanceAction,settings
from energy_copilot.maintenance.controller import run_maintenance
from energy_copilot.maintenance.evaluation import evaluate_controller,attribute_service

ROOT=Path('replay/maintenance_v1')
SPLIT=Path('configs/maintenance_split_v1.json')
MANIFEST=Path('configs/phase2f_readonly_manifest.json')
PILOTS=(MaintenancePolicy(.55,.55,1),MaintenancePolicy(.70,.70,1),MaintenancePolicy(.55,.55,2))


def guard():
    manifest=json.loads(MANIFEST.read_text())
    changed=[p for p,h in manifest.items() if not Path(p).is_file() or sha256(p)!=h]
    if changed:raise RuntimeError('Frozen upstream evidence changed: '+str(changed[:10]))
    return len(manifest)


def split():
    s=json.loads(SPLIT.read_text());groups=[set(s[k]) for k in ('development','validation','final')]
    if any(groups[i]&groups[j] for i in range(3) for j in range(i)):raise ValueError('Overlapping Phase II-F seeds')
    upstream=set(range(1,43))|set(range(101,126))|set(range(201,211))|set(range(1001,1007))|set(range(1101,1105))
    if any(g&upstream for g in groups):raise ValueError('Phase II-F seed overlaps upstream evidence')
    if s['horizon_days']!=30 or any(d<0 or d>=30 for d in s['calendar_days']):raise ValueError('Invalid evaluation horizon')
    return s


def original_input(seed,day,cfg,service):
    baseline=baseline_simulate(cfg,seed=seed,days=30)
    base=input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))
    delta=pd.Timedelta(days=day-7)
    template=replace(base,forecast_origin=(pd.Timestamp(base.forecast_origin)+delta).isoformat(),
       heats=tuple(replace(h,heat_id=h.heat_id.replace('D007',f'D{day:03d}')) for h in base.heats),
       tariff_calendar=tuple(replace(t,interval_start=(pd.Timestamp(t.interval_start)+delta).isoformat(),
                                    interval_end=(pd.Timestamp(t.interval_end)+delta).isoformat()) for t in base.tariff_calendar))
    inp,_=seed_input(template,baseline.readings,baseline.heats,baseline.production,values(cfg),service)
    return baseline,inp


def frozen_policy():
    node=json.loads((ROOT/'design_freeze.json').read_text());h=node.pop('design_sha256')
    if canonical_hash(node)!=h or node['config_sha256']!=sha256('configs/maintenance_v1.yaml') or node['split_sha256']!=sha256(SPLIT):
        raise ValueError('Maintenance design freeze has changed')
    if any(sha256(p)!=digest for p,digest in node['source_hashes'].items()):raise ValueError('Maintenance source changed after freeze')
    return MaintenancePolicy(**node['policy']).validate()


def one(seed,day,strategy,policy,folder,baseline=None,inp=None):
    cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    service=PredictionService('models/phase2b_v1')
    baseline,inp=(baseline,inp) if baseline is not None else original_input(seed,day,cfg,service)
    cal=json.loads(Path('replay/robustness_v1/duration_calibration.json').read_text())
    ep=json.loads(Path('replay/robustness_v1/design_freeze.json').read_text())['policy']
    robust=ReservePolicy(**ep)
    controller,controls=run_maintenance(inp,cfg,seed,30,service,robust,cal,policy,folder,strategy=strategy,grid=1)
    actions=tuple(MaintenanceAction(**a) for a in controller['maintenance_actions'])
    result,physical=evaluate_controller(strategy,baseline,inp,controller,controls,seed,30,folder,actions)
    result['maintenance_executed']=len(actions)
    result['maintenance_recommendations']=controller['maintenance_recommendations']
    write_json(folder/'replay_results.json',result)
    return result,physical,baseline,inp


def pilot(seed,day):
    s=split()
    if seed not in s['development'] or day not in s['calendar_days']:raise ValueError('Pilot restricted to development')
    if (ROOT/'design_freeze.json').exists():raise RuntimeError('Pilot policy design already frozen')
    guard();cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    service=PredictionService('models/phase2b_v1');baseline,inp=original_input(seed,day,cfg,service)
    reference=ROOT/'development_pilot'/f'seed_{seed}_day_{day}'/'F0'
    if not (reference/'replay_results.json').exists():
        result,_,_,_=one(seed,day,'F0',PILOTS[0],reference,baseline,inp)
        print('PILOT',seed,day,'F0',result['status'],flush=True)
    for policy in PILOTS:
        name=f'm{policy.mill_probability:g}_p{policy.pump_probability:g}_n{policy.persistence_observations}'
        directory=ROOT/'development_pilot'/f'seed_{seed}_day_{day}'/name
        if (directory/'replay_results.json').exists():continue
        result,_,_,_=one(seed,day,'F2',policy,directory,baseline,inp)
        print('PILOT',seed,day,name,result['status'],result.get('maintenance_executed'),flush=True)
    guard()


def freeze():
    if (ROOT/'design_freeze.json').exists():raise RuntimeError('Design is already frozen')
    s=split();expected={(2001,14),(2002,12)};observed=set()
    rows=[]
    for seed,day in expected:
        observed.add((seed,day))
        base_path=ROOT/'development_pilot'/f'seed_{seed}_day_{day}'/'F0'/'replay_results.json'
        if not base_path.is_file():raise ValueError('Missing development no-service reference '+str(base_path))
        base=json.loads(base_path.read_text())
        for policy in PILOTS:
            name=f'm{policy.mill_probability:g}_p{policy.pump_probability:g}_n{policy.persistence_observations}'
            p=ROOT/'development_pilot'/f'seed_{seed}_day_{day}'/name/'replay_results.json'
            if not p.is_file():raise ValueError('Missing development pilot '+str(p))
            r=json.loads(p.read_text());m=r['realized_metrics'];b=base['realized_metrics']
            rows.append(dict(seed=seed,day=day,policy=name,valid=r['status']=='physically_valid',
                reference_valid=base['status']=='physically_valid',executed=r.get('maintenance_executed',0),
                cost_Rs=None if m is None else m['physical_evaluation_tariff_cost_Rs'],
                bars_t=None if m is None else m['bar_t'],
                reference_bars_t=None if b is None else b['bar_t'],
                unavailable_hours=None if m is None else sum(m['downtime_hours'].values())+r.get('maintenance_executed',0)*.25,
                reference_unavailable_hours=None if b is None else sum(b['downtime_hours'].values())))
    summary=[]
    for policy in PILOTS:
        name=f'm{policy.mill_probability:g}_p{policy.pump_probability:g}_n{policy.persistence_observations}'
        rr=[r for r in rows if r['policy']==name];valid=[r for r in rr if r['valid']]
        summary.append(dict(policy=name,valid=len(valid),attempted=len(rr),services=sum(r['executed'] for r in rr),
            conditional_cost_Rs=None if not valid else sum(r['cost_Rs'] for r in valid)/len(valid),
            total_unavailable_hours=None if not valid else sum(r['unavailable_hours'] for r in valid),
            total_bars_t=None if not valid else sum(r['bars_t'] for r in valid)))
    # Declared operational selection: physical validity and production first;
    # then combined corrective + preventive downtime, then synthetic cost.
    selected=min(range(len(PILOTS)),key=lambda i:(-summary[i]['valid'],
                    float('inf') if summary[i]['total_bars_t'] is None else -summary[i]['total_bars_t'],
                    float('inf') if summary[i]['total_unavailable_hours'] is None else summary[i]['total_unavailable_hours'],
                    float('inf') if summary[i]['conditional_cost_Rs'] is None else summary[i]['conditional_cost_Rs'],
                    summary[i]['services'],PILOTS[i].persistence_observations))
    guard();source={str(p).replace('\\','/'):sha256(p) for p in sorted(Path('src/energy_copilot/maintenance').glob('*.py'))}
    source['scripts/phase2f.py']=sha256('scripts/phase2f.py')
    node=dict(policy=asdict(PILOTS[selected]),selection_rule='valid count, production, total unavailable hours, conditional synthetic cost, simplicity',
              pilot_seeds=[2001,2002],pilot_days=[14,12],pilot_summary=summary,
              config_sha256=sha256('configs/maintenance_v1.yaml'),split_sha256=sha256(SPLIT),
              upstream_manifest_sha256=sha256(MANIFEST),source_hashes=source,
              validation_used_for_selection=False,final_used_for_selection=False)
    node['design_sha256']=canonical_hash(node);write_json(ROOT/'development_pilot_summary.json',summary)
    write_json(ROOT/'design_freeze.json',node)
    print('FROZEN',node['policy'],flush=True)


def run(partition,seed,day):
    s=split();name={'development':'development','validation':'validation','final':'final'}[partition]
    if seed not in s[name] or day not in s['calendar_days']:raise ValueError('Seed/day does not belong to requested partition')
    if partition!='development':policy=frozen_policy()
    else:policy=frozen_policy() if (ROOT/'design_freeze.json').exists() else None
    if policy is None:raise RuntimeError('Freeze pilot design before main development evaluation')
    if partition=='final' and not (ROOT/'validation_comparison.json').exists():raise RuntimeError('Validation gate must pass before final seeds')
    guard();cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml');service=PredictionService('models/phase2b_v1')
    baseline,inp=original_input(seed,day,cfg,service);root=ROOT/partition/f'seed_{seed}_day_{day}'
    f0,f0sim,_,_=one(seed,day,'F0',policy,root/'F0',baseline,inp)
    # F1 is advisory-only. It reads the same public risk history recorded by F0,
    # makes no intervention, and therefore has exactly the same physical replay.
    f1=dict(f0,case='F1',advisory_only=True,advice_source='F0 public closed-history health_prediction_history.parquet',
            physical_controls_sha256=controls_hash(root/'F0'/'controller_result.json'))
    write_json(root/'F1'/'replay_results.json',f1)
    f2,f2sim,_,_=one(seed,day,'F2',policy,root/'F2',baseline,inp)
    actions=tuple(MaintenanceAction(**a) for a in f2.get('maintenance_actions',()))
    attribution=attribute_service(f0sim,f2sim,actions)
    pd.DataFrame(attribution).to_parquet(root/'maintenance_attribution.parquet',index=False)
    write_json(root/'attempt_results.json',[dict(seed=seed,day=day,strategy=k,result=v) for k,v in [('F0',f0),('F1',f1),('F2',f2)]])
    print(partition,seed,day,[(k,v['status'],v.get('maintenance_executed',0)) for k,v in [('F0',f0),('F1',f1),('F2',f2)]],flush=True)
    guard()


def controls_hash(path):
    return canonical_hash(json.loads(Path(path).read_text())['controls'])


def regress_e4(seed,day):
    s=split()
    if seed not in s['development'] or day not in s['calendar_days']:raise ValueError('E4 regression is development-only')
    guard();cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml');service=PredictionService('models/phase2b_v1')
    baseline,inp=original_input(seed,day,cfg,service)
    cal=json.loads(Path('replay/robustness_v1/duration_calibration.json').read_text())
    frozen=json.loads(Path('replay/robustness_v1/design_freeze.json').read_text())
    folder=ROOT/'e4_regression'/f'seed_{seed}_day_{day}'
    ctrl,controls=run_adaptive(inp,cfg,seed,30,service,ReservePolicy(**frozen['policy']),cal,folder,robust=True,grid=1)
    result=evaluate_adaptive('E4_frozen',baseline,inp,ctrl,controls,seed,30,folder)
    f0_folder=ROOT/'development_pilot'/f'seed_{seed}_day_{day}'/'F0'
    if not (f0_folder/'controller_result.json').is_file():raise ValueError('F0 reference missing')
    original=json.loads((f0_folder/'controller_result.json').read_text())
    frozen_controls=json.loads((folder/'controller_result.json').read_text())['controls']
    equivalent=all(original['controls'][name]==frozen_controls[name] for name in ('schedule','practice_by_day','rolling_dispatch'))
    f0=json.loads((f0_folder/'replay_results.json').read_text())
    metrics_equal=result.get('realized_metrics')==f0.get('realized_metrics')
    proof=dict(seed=seed,day=day,controls_identical=equivalent,physical_metrics_identical=metrics_equal,
               status_identical=result['status']==f0['status'],frozen_E4_status=result['status'],F0_status=f0['status'])
    write_json(folder/'e4_f0_equivalence.json',proof)
    if not all((equivalent,metrics_equal,proof['status_identical'])):raise RuntimeError('F0 differs from frozen E4')
    guard();print('E4/F0 regression PASS',seed,day,flush=True)


def summarize(partition):
    s=split();roots=[ROOT/partition/f'seed_{seed}_day_{day}'/'attempt_results.json' for seed in s[partition] for day in s['calendar_days']]
    missing=[str(p) for p in roots if not p.is_file()]
    if missing:raise RuntimeError('Cannot omit failed or missing cases: '+str(missing))
    rows=[r for p in roots for r in json.loads(p.read_text())]
    comparison={};fail=[];attribution=[];paired=[]
    for seed in s[partition]:
        for day in s['calendar_days']:
            root=ROOT/partition/f'seed_{seed}_day_{day}'
            path=root/'maintenance_attribution.parquet'
            if path.is_file():
                attribution.extend(dict(seed=seed,day=day,**row) for row in pd.read_parquet(path).to_dict('records'))
            case=[r for r in rows if r['seed']==seed and r['day']==day]
            f0=next(r['result'] for r in case if r['strategy']=='F0')
            f2=next(r['result'] for r in case if r['strategy']=='F2')
            if f0['status']=='physically_valid' and f2['status']=='physically_valid':
                a=f0['realized_metrics'];b=f2['realized_metrics']
                paired.append(dict(seed=seed,day=day,energy_delta_kWh=b['total_kWh']-a['total_kWh'],
                    synthetic_tariff_delta_Rs=b['physical_evaluation_tariff_cost_Rs']-a['physical_evaluation_tariff_cost_Rs'],
                    bar_delta_t=b['bar_t']-a['bar_t'],
                    corrective_downtime_delta_hours=sum(b['downtime_hours'].values())-sum(a['downtime_hours'].values()),
                    preventive_service_hours=f2.get('maintenance_executed',0)*.25))
    for strategy in ('F0','F1','F2'):
        rr=[r for r in rows if r['strategy']==strategy];valid=[r['result'] for r in rr if r['result']['status']=='physically_valid']
        metrics=[r['realized_metrics'] for r in valid]
        comparison[strategy]=dict(attempted=len(rr),physically_valid=len(valid),feasibility_rate=len(valid)/len(rr),
          maintenance_count=sum(r['result'].get('maintenance_executed',0) for r in rr),
          mean_replans=sum(r['result']['replans'] for r in rr)/len(rr),
          conditional_mean_total_kWh=None if not metrics else sum(m['total_kWh'] for m in metrics)/len(metrics),
          conditional_mean_synthetic_cost_Rs=None if not metrics else sum(m['physical_evaluation_tariff_cost_Rs'] for m in metrics)/len(metrics),
          conditional_mean_production_t=None if not metrics else sum(m['bar_t'] for m in metrics)/len(metrics),
          conditional_mean_corrective_downtime_hours=None if not metrics else sum(sum(m['downtime_hours'].values()) for m in metrics)/len(metrics),
          conditional_mean_total_unavailability_hours=None if not metrics else sum(sum(r['realized_metrics']['downtime_hours'].values())+r.get('maintenance_executed',0)*.25 for r in valid)/len(valid),
          conditional_mean_peak_kVA=None if not metrics else sum(m['peak_piecewise_kVA'] for m in metrics)/len(metrics))
        for r in rr:
            if r['result']['status']!='physically_valid':fail.append(dict(seed=r['seed'],day=r['day'],strategy=strategy,
                 status=r['result']['status'],cause=r['result'].get('failure_class'),reason=r['result'].get('reason'),retained=True))
    comparison['F2']['absolute_feasibility_change_vs_F0']=comparison['F2']['feasibility_rate']-comparison['F0']['feasibility_rate']
    comparison['F2']['conditional_cost_difference_Rs_vs_F0']=(None if comparison['F2']['conditional_mean_synthetic_cost_Rs'] is None or comparison['F0']['conditional_mean_synthetic_cost_Rs'] is None else
        comparison['F2']['conditional_mean_synthetic_cost_Rs']-comparison['F0']['conditional_mean_synthetic_cost_Rs'])
    comparison['paired_physically_valid_cases']=len(paired)
    comparison['paired_mean_energy_delta_kWh']=None if not paired else sum(r['energy_delta_kWh'] for r in paired)/len(paired)
    comparison['paired_mean_synthetic_tariff_delta_Rs']=None if not paired else sum(r['synthetic_tariff_delta_Rs'] for r in paired)/len(paired)
    comparison['service_attribution_counts']={name:sum(r['classification']==name for r in attribution) for name in
        ('averted_within_24h','unnecessary_24h','failure_despite_service','undetermined_counterfactual')}
    write_json(ROOT/f'{partition}_comparison.json',comparison)
    pd.DataFrame(fail).to_parquet(ROOT/f'{partition}_failure_analysis.parquet',index=False)
    pd.DataFrame(attribution).to_parquet(ROOT/f'{partition}_maintenance_attribution.parquet',index=False)
    pd.DataFrame(paired).to_parquet(ROOT/f'{partition}_paired_deltas.parquet',index=False)
    guard();print(partition,comparison,flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['pilot','freeze','regress-e4','development','validation','final','summarize-development','summarize-validation','summarize-final']);
    parser.add_argument('--seed',type=int);parser.add_argument('--day',type=int);a=parser.parse_args()
    if a.stage in ('pilot','regress-e4','development','validation','final') and (a.seed is None or a.day is None):parser.error('These stages require --seed and --day')
    if a.stage=='pilot':pilot(a.seed,a.day)
    elif a.stage=='regress-e4':regress_e4(a.seed,a.day)
    elif a.stage=='freeze':freeze()
    elif a.stage.startswith('summarize-'):summarize(a.stage.split('-',1)[1])
    else:run(a.stage,a.seed,a.day)


if __name__=='__main__':main()
