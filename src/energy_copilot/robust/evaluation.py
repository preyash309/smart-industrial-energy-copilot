"""Evaluation-only full twin/checker. This module never constructs predictor features."""
from pathlib import Path
from dataclasses import asdict
import pandas as pd
from energy_copilot.common import write_json
from energy_copilot.replay.runner import replay_case
from energy_copilot.replay.scenarios import scenario_proof
from energy_copilot.replay.adapter import ReplayControls,adapt_plan


def classify_failure(reason):
    text=(reason or '').lower()
    if 'overlapping' in text:return 'duration_miss_overlap'
    if 'cannot complete' in text or 'end-of-day' in text:return 'end_of_day_overrun'
    if 'rolling exceeds' in text or 'billet' in text or 'stock' in text:return 'inventory_or_rolling_availability'
    if 'contract' in text or 'demand' in text:return 'demand_exceedance'
    if 'cooling' in text:return 'cooling_or_equipment_outage'
    if 'feasible' in text or 'eligible' in text:return 'solver_infeasibility'
    return 'unsupported_control_or_execution_failure'


def evaluate_plan(name,baseline,inp,plan,seed,days,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);write_json(out/'initial_plan.json',plan.to_dict())
    if not plan.releasable:
        entry=dict(case=name,status='optimizer_infeasible',reason=plan.reason,realized_metrics=None,retained=True)
    else:
        control=adapt_plan(inp,plan,baseline.config)
        entry,_=replay_case(name,baseline,inp,control,seed,days,scenario_proof(baseline.config,seed,days),result=plan)
        write_json(out/'controls.json',control.to_dict())
    entry['failure_class']=None if entry['status']=='physically_valid' else classify_failure(entry.get('reason',entry.get('violation')))
    write_json(out/'replay_results.json',entry);return entry


def evaluate_adaptive(name,baseline,inp,controller,controls,seed,days,out):
    if controller['status']!='continuation_complete':
        entry=dict(case=name,status='no_feasible_continuation',reason=controller['reason'],realized_metrics=None,retained=True,
                   completed_heats=controller['completed_heats'],replans=controller['replans'])
    else:
        entry,sim=replay_case(name,baseline,inp,controls,seed,days,scenario_proof(baseline.config,seed,days))
        entry['replans']=controller['replans'];entry['completed_heats']=controller['completed_heats']
        if sim is not None:
            # Executed public heat logs must equal final independent replay.
            public=pd.read_parquet(Path(out)/'prediction_history.parquet')
            h=sim.heats[sim.heats.heat_id.isin(public.heat_id)].copy()
            h['duration_min']=(h.end-h.start).dt.total_seconds()/60
            joined=public.merge(h[['heat_id','end','duration_min']],on='heat_id',validate='one_to_one')
            residual=joined.duration_min-joined.duration_p50_min
            entry['duration_prediction_metrics']=dict(MAE=float(residual.abs().mean()),bias=float(residual.mean()),p90_exceedance=float((joined.duration_min>joined.duration_p90_min).mean()))
            entry['actual_end_margin_min']=float((pd.Timestamp(controls.end)-h.end.max()).total_seconds()/60)
            joined.to_parquet(Path(out)/'executed_heat_evaluation.parquet',index=False)
    entry['failure_class']=None if entry['status']=='physically_valid' else classify_failure(entry.get('reason',entry.get('violation')))
    write_json(Path(out)/'replay_results.json',entry);return entry


def compare_all(rows):
    result={}
    for strategy in ('E0','E1','E2','E3','E4'):
        selected=[r for r in rows if r['strategy']==strategy];valid=[r for r in selected if r['result']['status']=='physically_valid']
        metrics=[r['result']['realized_metrics'] for r in valid]
        def distribution(key):
            x=pd.Series([m[key] for m in metrics],dtype=float)
            return dict(n=len(x),mean=None if x.empty else float(x.mean()),min=None if x.empty else float(x.min()),max=None if x.empty else float(x.max()))
        result[strategy]=dict(attempted=len(selected),feasible=len(valid),feasibility_rate=len(valid)/len(selected) if selected else None,
            completed_production_rate=len(valid)/len(selected) if selected else None,conditional_on_feasible={k:distribution(k) for k in ('total_kWh','IF_SEC_kWh_per_t','plant_kWh_per_t_bars','physical_evaluation_tariff_cost_Rs','inventory_min_t','final_inventory_t','IF_idle_hours','IF_utilization')},
            total_replans=sum(r['result'].get('replans',0) for r in selected),no_feasible_continuations=sum(r['result']['status']=='no_feasible_continuation' for r in selected),
            failures=[dict(seed=r['seed'],cause=r['result'].get('failure_class'),reason=r['result'].get('reason',r['result'].get('violation'))) for r in selected if r['result']['status']!='physically_valid'])
    if result['E0']['feasibility_rate'] is not None:
        b=result['E0']['feasibility_rate']
        for s in result:
            f=result[s]['feasibility_rate'];result[s]['absolute_feasibility_improvement']=None if f is None else f-b
            result[s]['relative_feasibility_improvement']=None if not b or f is None else (f-b)/b
    return result
