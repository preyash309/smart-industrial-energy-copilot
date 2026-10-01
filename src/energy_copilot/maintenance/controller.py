"""Commit one heat and due services; advance, observe, replan. No future oracle."""
from dataclasses import asdict,replace
from pathlib import Path
import pandas as pd
from energy_copilot.common import write_json,values
from energy_copilot.replay.adapter import ReplayControls
from .execution import simulate as execute_prefix
from energy_copilot.robust.state_update import public_snapshot,update_state,remaining_input
from energy_copilot.robust.robust_model import optimize_robust
from energy_copilot.robust.scenarios import make_scenarios
from .optimizer import optimize_maintenance
from .policy import eligible_assets
from .contracts import settings


def run_maintenance(template,config,seed,days,service,robust_policy,calibration,maintenance_policy,out,
                    strategy='F2',grid=1,maintenance_config=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);origin=pd.Timestamp(template.forecast_origin)
    plant=values(config);day=(origin-pd.Timestamp(plant['start'])).days
    maintenance_config=maintenance_config or settings()
    if strategy not in ('F0','F1','F2'):raise ValueError('Unknown maintenance strategy')
    current=origin;state=None;starts={};dispatch={};executed=[];feed=[];states=[];predictions=[];history=[];previous_plan=None
    executed_services=[];health_history=[];candidates_history=[];decisions=[];recommendations=[]
    practice_loss=service.contract['practice_modes']['practice_loss_40']['practice_loss_kWh_t']
    # The executor knows the seed; the planner receives only public_snapshot.
    initial=execute_prefix(config,seed=seed,days=days)
    snapshot=public_snapshot(initial,current);state=update_state(None,current,snapshot[1],feed,executed,template)
    reason=None;step=0;prefix_hashes=[]
    while state.remaining_heats and current<origin+pd.Timedelta(days=1):
        not_before=None
        if executed and previous_plan is not None:
            prior_row=previous_plan.schedule[0]
            last_prediction=next(k.prediction for k in inp.heat_candidates if k.candidate_id==prior_row['candidate_id'])
            not_before=pd.Timestamp(executed[-1]['end'])+pd.Timedelta(minutes=robust_policy.buffer(last_prediction))
        inp,provenance=remaining_input(template,state,snapshot,plant,service,grid=grid,not_before=not_before)
        scenarios=make_scenarios(calibration,state.remaining_heats)
        eligible,audit=eligible_assets(inp.health_predictions,snapshot[0],current,maintenance_policy,health_history,
                                       already_serviced=[a.asset_id for a in executed_services])
        for row in audit:health_history.append(dict(step=step,**row))
        if strategy=='F2':planned=optimize_maintenance(inp,robust_policy,scenarios,eligible,maintenance_config,executed_services)
        else:planned=optimize_robust(inp,robust_policy,scenarios)
        plan=planned.plan
        aux=snapshot[0].loc[snapshot[0].asset_id.eq('AUX')].tail(4)
        recent=tuple(dict(interval_end=(r.timestamp+pd.Timedelta(minutes=15)).isoformat(),kW=None if pd.isna(r.kW) or r.sensor_glitch else float(r.kW)) for r in aux.itertuples())
        state=replace(state,observed_recent_load=recent,latest_health_state=plan.health_context)
        record=dict(step=step,current_time=state.current_time,available_information=provenance,state=asdict(state),
                    prediction_version=inp.prediction_version,predictions=[asdict(k.prediction) for k in inp.heat_candidates if k.start==state.current_time],
                    uncertainty_assumptions=asdict(robust_policy),scenarios=[asdict(s) for s in scenarios],remaining_heats=state.remaining_heats,
                    selected_schedule=plan.schedule,binding_constraints=plan.active_constraints,reason='initial plan' if step==0 else 'heat completion posted; closed meter slots only; current-slot rolling locked',status=plan.status,
                    accounting_geometry_start=inp.forecast_origin,known_current_slot_arrivals=inp.known_arrivals,committed_current_slot_feed_t=inp.committed_first_feed_t,
                    accounting_scope='Unexecuted heat energy plus remaining slot ledger; committed current-slot services are constants. Completed IF meter energy is historical, not a decision coefficient.',
                    health_audit=audit,maintenance_eligible=eligible,maintenance_candidates=[asdict(a) for a in getattr(planned,'candidates',())],
                    selected_maintenance=[asdict(a) for a in getattr(planned,'actions',())],executed_maintenance=[asdict(a) for a in executed_services],
                    maintenance_policy=asdict(maintenance_policy),strategy=strategy)
        write_json(out/('initial_plan.json' if step==0 else f'replan_step_{step:02d}.json'),record)
        states.append(dict(step=step,current_time=current,inventory_t=state.actual_inventory_t,completed_heats=len(state.completed_heats),remaining_heats=len(state.remaining_heats),bars_t=sum(feed)*inp.constraints.rolling_yield,completed_services=len(executed_services)))
        for candidate in getattr(planned,'candidates',()):candidates_history.append(dict(step=step,decision_time=current,asset_id=candidate.asset_id,start_time=candidate.start_time,end_time=candidate.end_time,selected=candidate in planned.actions,model_version=inp.prediction_version,calibrated_probability=next(p.calibrated_probability for p in inp.health_predictions if p.asset_id==candidate.asset_id)))
        for candidate in getattr(planned,'actions',()):recommendations.append(dict(step=step,decision_time=current,action=candidate,health=next(r for r in audit if r['asset_id']==candidate.asset_id),alternatives=tuple(c for c in getattr(planned,'candidates',()) if c.asset_id==candidate.asset_id),binding=plan.active_constraints,expected=plan.predicted_metrics))
        if not plan.releasable:
            reason=plan.reason or plan.status;break
        history.extend(dict(step=step,committed=(i==0),**r) for i,r in enumerate(plan.schedule))
        first=plan.schedule[0];starts[first['heat_id']]=first['start'];ordinal=len(starts)
        predictions.append(dict(step=step,available_at=current,heat_id=first['heat_id'],model_version=inp.prediction_version,
                                start=first['start'],duration_p50_min=first['duration_p50_min'],duration_p90_min=first['duration_p90_min'],energy_p50_kWh=first['energy_p50_kWh']))
        # First advance heat execution with zero FUTURE rolling. Heat physics does
        # not depend on rolling; no future fault/state escapes the public gate.
        limits={d:0 for d in range(day+1,days)};limits[day]=ordinal
        # Only previously committed service and service completed BEFORE the
        # selected heat's start can affect its duration. No future action or
        # failure realization is allowed to choose the next decision.
        preliminary=tuple(executed_services)+tuple(a for a in getattr(planned,'actions',()) if pd.Timestamp(a.end_time)<=pd.Timestamp(first['start']))
        try:
            probe=execute_prefix(config,schedule=starts,practice_by_day={day:practice_loss},rolling_dispatch={day*96+t:feed[t] for t in range(len(feed))},
                                 heat_limits=limits,seed=seed,days=days,maintenance_actions=preliminary,maintenance_config=maintenance_config)
        except ValueError as exc:
            reason=str(exc);break
        heat=probe.heats.loc[probe.heats.heat_id.eq(first['heat_id'])].iloc[0]
        boundary=pd.Timestamp(heat.end)
        if boundary>origin+pd.Timedelta(days=1):reason='end-of-day overrun';break
        new_actions=[a for a in getattr(planned,'actions',()) if pd.Timestamp(a.start_time)<boundary and a not in executed_services]
        if any(a.asset_id=='PMP_01' and pd.Timestamp(a.end_time)>pd.Timestamp(first['start']) and pd.Timestamp(a.start_time)<boundary for a in new_actions):
            reason='Pump service window conflicts with realized heat duration; action not executed';break
        for a in new_actions:
            executed_services.append(a)
            recommendation=next(r for r in reversed(recommendations) if r['action']==a)
            decisions.append(dict(step=step,decision_time=recommendation['decision_time'],asset_id=a.asset_id,start_time=a.start_time,end_time=a.end_time,
                                  intervention_type=a.intervention_type,condition_effect=a.condition_effect,model_version=inp.prediction_version,
                                  predicted_probability=recommendation['health']['calibrated_probability'],policy_threshold=recommendation['health']['threshold'],
                                  public_health_evidence=recommendation['health']['visible_evidence'],alternative_windows=[x.start_time for x in recommendation['alternatives']],
                                  binding_constraints=recommendation['binding'],expected_production_t=recommendation['expected'].get('bars_t'),
                                  expected_energy_kWh=recommendation['expected'].get('total_kWh'),expected_synthetic_cost_Rs=recommendation['expected'].get('tariff_cost_Rs'),
                                  executed=True,final_replay_outcome=None))
        if any(pd.Timestamp(a.end_time)>boundary for a in executed_services):
            boundary=max([boundary,*[pd.Timestamp(a.end_time) for a in executed_services]])
            if boundary>origin+pd.Timedelta(days=1):reason='Committed service completes beyond working day';break
        import math
        end_slot=math.ceil((boundary-origin).total_seconds()/900);offset=int((pd.Timestamp(inp.forecast_origin)-origin).total_seconds()/900)
        # Execute previously selected rolling through that boundary. If the heat
        # overruns its nominal finish, retain the same plan commands, never peek
        # at future billets to repair the dispatch.
        for t in range(len(feed),end_slot):
            v=plan.load_trajectory[t-offset]['rolling_billet_t'];feed.append(v);dispatch[day*96+t]=v
        try:
            partial=execute_prefix(config,schedule=starts,practice_by_day={day:practice_loss},rolling_dispatch=dispatch,
                                   heat_limits=limits,seed=seed,days=days,maintenance_actions=tuple(executed_services),maintenance_config=maintenance_config)
        except ValueError as exc:
            reason=str(exc);break
        # Keep only public history and accepted command acknowledgements.
        current=boundary;snapshot=public_snapshot(partial,current)
        executed.append(dict(heat_id=first['heat_id'],start=first['start'],end=pd.Timestamp(heat.end).isoformat()))
        state=update_state(state,current,snapshot[1],feed,executed,template)
        previous_plan=plan;step+=1
    # After the last heat, lock all remaining rolling from the last checked plan.
    if not state.remaining_heats and previous_plan is not None:
        prior=pd.Timestamp(previous_plan.forecast_origin);off=int((prior-origin).total_seconds()/900)
        for t in range(len(feed),96):dispatch[day*96+t]=previous_plan.load_trajectory[t-off]['rolling_billet_t']
        # Service after the final heat is still a committed future decision of
        # the last checked plan; full replay will judge whether it can execute.
        for a in getattr(planned,'actions',()):
            if a not in executed_services and origin<=pd.Timestamp(a.start_time)<origin+pd.Timedelta(days=1):
                executed_services.append(a)
                recommendation=next(r for r in reversed(recommendations) if r['action']==a)
                decisions.append(dict(step=step-1,decision_time=recommendation['decision_time'],asset_id=a.asset_id,start_time=a.start_time,end_time=a.end_time,
                                      intervention_type=a.intervention_type,condition_effect=a.condition_effect,model_version=inp.prediction_version,
                                      predicted_probability=recommendation['health']['calibrated_probability'],policy_threshold=recommendation['health']['threshold'],
                                      public_health_evidence=recommendation['health']['visible_evidence'],alternative_windows=[x.start_time for x in recommendation['alternatives']],
                                      binding_constraints=recommendation['binding'],expected_production_t=recommendation['expected'].get('bars_t'),
                                      expected_energy_kWh=recommendation['expected'].get('total_kWh'),expected_synthetic_cost_Rs=recommendation['expected'].get('tariff_cost_Rs'),
                                      executed=True,final_replay_outcome=None))
    for name,rows in [('state_history',states),('prediction_history',predictions),('schedule_history',history),
                      ('health_prediction_history',health_history),('maintenance_candidate_history',candidates_history),('maintenance_decisions',decisions)]:
        pd.DataFrame(rows).to_parquet(out/f'{name}.parquet',index=False)
    controls=ReplayControls(starts,{day:practice_loss},dispatch,'Adaptive exact committed heat/rolling ledger; final independent verification mandatory',origin.isoformat(),(origin+pd.Timedelta(days=1)).isoformat())
    result=dict(status='continuation_complete' if not state.remaining_heats and reason is None else 'no_feasible_continuation',reason=reason,replans=max(0,len(states)-1),completed_heats=len(state.completed_heats),
                states=len(states),controls=controls.to_dict(),maintenance_actions=[asdict(a) for a in executed_services],
                maintenance_recommendations=len(recommendations),maintenance_executed=len(executed_services),
                final_state=asdict(state),retained=True)
    write_json(out/'controller_result.json',result)
    return result,controls
