"""Evaluation-only matched-condition physical replay; no truth enters planning."""
from pathlib import Path
import pandas as pd
from energy_copilot.common import write_json
from energy_copilot.replay.compare import realized_metrics
from energy_copilot.robust.evaluation import classify_failure
from .execution import simulate,InvariantError
from .checker import verify_maintenance


def classify_maintenance_failure(reason):
    text=(reason or '').lower()
    if 'preventive service' in text and 'overlap' in text:return 'service_corrective_repair_overlap'
    if 'service window conflicts' in text or 'service overlaps' in text:return 'service_heat_overlap'
    if 'service' in text and 'rolling' in text:return 'service_rolling_conflict'
    return classify_failure(reason)


def evaluate_controller(name,baseline,inp,controller,controls,seed,days,out,actions=()):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    origin=pd.Timestamp(inp.forecast_origin);end=origin+pd.Timedelta(days=1)
    if baseline.scenario_manifest['seed']!=seed or baseline.scenario_manifest['days']!=days:
        raise ValueError('Baseline does not match evaluation seed and horizon')
    if pd.Timestamp(controls.origin)!=origin or pd.Timestamp(controls.end)!=end:
        raise ValueError('Controls do not match evaluation day')
    if any(pd.Timestamp(a.start_time)<origin or pd.Timestamp(a.start_time)>=end for a in actions):
        raise ValueError('Service outside evaluation day')
    if controller['status']!='continuation_complete':
        entry=dict(case=name,status='no_feasible_continuation',reason=controller['reason'],
                   completed_heats=controller['completed_heats'],replans=controller['replans'],
                   realized_metrics=None,maintenance_actions=[a.__dict__ for a in actions],retained=True)
        entry['failure_class']=classify_maintenance_failure(entry['reason'])
        write_json(out/'replay_results.json',entry)
        return entry,None
    try:
        sim=simulate(baseline.config,schedule=controls.schedule,seed=seed,days=days,
                     practice_by_day=controls.practice_by_day,rolling_dispatch=controls.rolling_dispatch,
                     maintenance_actions=actions)
    except (InvariantError,ValueError) as exc:
        entry=dict(case=name,status='replay_infeasible',reason=str(exc),failure_class=classify_maintenance_failure(str(exc)),
                   completed_heats=controller['completed_heats'],replans=controller['replans'],
                   realized_metrics=None,maintenance_actions=[a.__dict__ for a in actions],retained=True)
        write_json(out/'replay_results.json',entry)
        return entry,None
    original_hash=baseline.scenario_manifest['scenario_sha256']
    checked=verify_maintenance(sim,inp,actions,controls,original_exogenous_sha256=original_hash)
    # Upstream history is fixed because controls and actions are confined to this
    # day. Compare actual prefix rows as an additional independent proof.
    pre=sim.latent_heats[sim.latent_heats.end.le(origin)].reset_index(drop=True)
    reference=baseline.latent_heats[baseline.latent_heats.end.le(origin)].reset_index(drop=True)
    history_equal=pre.equals(reference)
    metrics,ledger=realized_metrics(sim,inp,checked['physical'])
    passed=checked['feasible'] and history_equal
    entry=dict(case=name,status='physically_valid' if passed else 'replay_infeasible',
               reason=None if passed else 'Independent physical/service/history checker failed',
               failure_class=None if passed else 'physical_checker_failure',
               completed_heats=controller['completed_heats'],replans=controller['replans'],
               realized_metrics=metrics,verification=checked,
               matched_conditions=dict(original_exogenous_sha256=original_hash,
                   replay_exogenous_sha256=sim.scenario_manifest.get('exogenous_scenario_sha256',sim.scenario_manifest['scenario_sha256']),
                   history_prefix_identical=history_equal,seed=seed,days=days,
                   synthetic_action_changes_wear_tape=bool(actions)),
               maintenance_actions=[a.__dict__ for a in actions],retained=True)
    public=pd.read_parquet(out/'prediction_history.parquet')
    if len(public):
        h=sim.heats[sim.heats.heat_id.isin(public.heat_id)].copy()
        h['actual_duration_min']=(h.end-h.start).dt.total_seconds()/60
        joined=public.merge(h[['heat_id','end','actual_duration_min']],on='heat_id',validate='one_to_one')
        error=joined.actual_duration_min-joined.duration_p50_min
        entry['duration_prediction_metrics']=dict(MAE=float(error.abs().mean()),bias=float(error.mean()),
            p90_exceedance=float((joined.actual_duration_min>joined.duration_p90_min).mean()),
            realized_vs_planned_finish_error_min=float(error.mean()))
        joined.to_parquet(out/'executed_heat_evaluation.parquet',index=False)
    failures=sim.events[sim.events.type.eq('failure')&sim.events.asset_id.isin(('MILL_01','PMP_01'))]
    services=sim.events[sim.events.type.eq('preventive_service')]
    entry['failure_events_day']=[dict(asset_id=r.asset_id,start=str(r.start),end=str(r.end)) for r in failures.itertuples() if origin<=r.start<end]
    entry['service_events_day']=[dict(asset_id=r.asset_id,start=str(r.start),end=str(r.end)) for r in services.itertuples() if origin<=r.start<end]
    sim.write(out/'simulation');ledger.to_parquet(out/'realized_tariff_ledger.parquet',index=False)
    write_json(out/'replay_results.json',entry)
    return entry,sim


def attribute_service(f0_sim,f2_sim,actions,horizon_hours=24):
    """Same-seed no-action counterfactual, not a real-world causal estimate."""
    if f0_sim is None or f2_sim is None:
        return [dict(asset_id=a.asset_id,service_start=a.start_time,no_action_failure_within_24h=None,
                     service_run_failure_within_24h=None,classification='undetermined_counterfactual',
                     no_action_failure_times=[],service_run_failure_times=[],
                     evidence='At least one full physical replay failed; no avoided-failure claim') for a in actions]
    rows=[]
    for action in actions:
        at=pd.Timestamp(action.start_time);end=at+pd.Timedelta(hours=horizon_hours)
        base=f0_sim.events[(f0_sim.events.type=='failure')&(f0_sim.events.asset_id==action.asset_id)&
                           (f0_sim.events.start>=at)&(f0_sim.events.start<end)]
        successor=f2_sim.events[(f2_sim.events.type=='failure')&(f2_sim.events.asset_id==action.asset_id)&
                                (f2_sim.events.start>=at)&(f2_sim.events.start<end)]
        rows.append(dict(asset_id=action.asset_id,service_start=action.start_time,
                         no_action_failure_within_24h=bool(len(base)),service_run_failure_within_24h=bool(len(successor)),
                         classification=('averted_within_24h' if len(base) and not len(successor) else
                                         'unnecessary_24h' if not len(base) else 'failure_despite_service'),
                         no_action_failure_times=[str(x) for x in base.start],
                         service_run_failure_times=[str(x) for x in successor.start],
                         evidence='matched synthetic seed; service re-draws wear life; attribution limited to configured 24-hour horizon'))
    return rows
