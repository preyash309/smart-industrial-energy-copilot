"""Retain failed original plans; no repair/reoptimization or seed substitution."""
from pathlib import Path
import json
import pandas as pd
from energy_copilot.common import write_json,canonical_hash,values
from energy_copilot.sim.engine import InvariantError as FrozenInvariantError
from .compatible_v111 import simulate, InvariantError
from .adapter import ReplayControls
from .origin_state import before_origin,match_manifest
from .checker import verify_physics
from .compare import realized_metrics
from .forecast_error import compare_forecast,heat_comparison,errors


def replay_case(name, baseline, inp, controls, seed, days, scenario_proof, output=None, result=None):
    c=values(baseline.config);origin=pd.Timestamp(inp.forecast_origin)
    end=origin+pd.Timedelta(days=1);day=(origin-pd.Timestamp(c['start'])).days
    if baseline.scenario_manifest['seed']!=seed or baseline.scenario_manifest['days']!=days or scenario_proof['seed']!=seed or scenario_proof['days']!=days:
        raise ValueError('Matched seed/horizon mismatch')
    if baseline.scenario_manifest['scenario_sha256']!=scenario_proof['scenario_sha256']:
        raise ValueError('Exogenous scenario proof mismatch')
    if pd.Timestamp(controls.origin)!=origin or pd.Timestamp(controls.end)!=end:
        raise ValueError('Controls differ from optimizer horizon')
    if set(controls.practice_by_day)-{day} or any(not origin<=pd.Timestamp(t)<end for t in controls.schedule.values()):
        raise ValueError('Controls would modify common history or another day')
    expected={h.heat_id for h in inp.heats}
    if controls.schedule and set(controls.schedule)!=expected:raise ValueError('Exact replay heat identities mismatch')
    contract=json.loads(Path('models/phase2b_v1/prediction_contract.json').read_text())
    permitted={v['practice_loss_kWh_t'] for v in contract['practice_modes'].values()}
    if any(v not in permitted for v in controls.practice_by_day.values()):raise ValueError('Unsupported practice value')
    lo=day*1440//c['clock_minutes'];hi=lo+1440//c['clock_minutes']
    if any(not lo<=i<hi for i in controls.rolling_dispatch):raise ValueError('Rolling control outside replay day')
    if controls.rolling_dispatch and set(controls.rolling_dispatch)!=set(range(lo,hi)):
        raise ValueError('Exact rolling replay requires all slots, including zeros')
    directory=Path(output) if output else None
    if directory:
        directory.mkdir(parents=True,exist_ok=True)
        write_json(directory/'controls.json',controls.to_dict())
        if result:write_json(directory/'optimizer_result.json',result.to_dict())
    try:
        sim=simulate(baseline.config,schedule=controls.schedule,seed=seed,days=days,
                     practice_by_day=controls.practice_by_day,rolling_dispatch=controls.rolling_dispatch)
    except (InvariantError,FrozenInvariantError) as exc:
        # Inspect only the failed evaluation frame, never resubmit changed controls.
        trace=exc.__traceback__;local={}
        while trace:
            if trace.tb_frame.f_code.co_name=='simulate':local=trace.tb_frame.f_locals
            trace=trace.tb_next
        heat_trace=pd.DataFrame(local.get('heatrows',[]))
        diagnostic={k:local[k] for k in ('heat_id','heatstart','cursor','end','i','yard','feed','requested_feed') if k in local}
        if 'ts' in local:diagnostic['timestamp']=str(local['ts'])
        tape=local.get('tape',{})
        proof=dict(status='PASS' if tape.get('hash')==scenario_proof['scenario_sha256'] else 'FAIL',
            scenario_identical=tape.get('hash')==scenario_proof['scenario_sha256'],scenario=scenario_proof,
            origin_state=before_origin(baseline,controls.origin),
            history_identical='proven by baseline recreation plus controls scoped after origin; failed branch prefix heat hashes below',
            executed_history_heat_rows=int((heat_trace.end<=pd.Timestamp(controls.origin)).sum()) if not heat_trace.empty else 0,
            controls=controls.to_dict(),controls_sha256=controls.sha256,
            production_order_sha256=canonical_hash(inp.production_order.__dict__),tariff_sha256=canonical_hash([t.__dict__ for t in inp.tariff_calendar]))
        if not heat_trace.empty:
            prefix=heat_trace[heat_trace.end<=pd.Timestamp(controls.origin)]
            reference=baseline.latent_heats[baseline.latent_heats.end<=pd.Timestamp(controls.origin)]
            proof['prefix_heat_state_identical']=prefix.reset_index(drop=True).equals(reference.reset_index(drop=True))
            if not proof['prefix_heat_state_identical']:proof['status']='FAIL'
        reason=str(exc);category='duration underprediction' if 'overlapping' in reason or 'cannot complete' in reason else 'inventory timing mismatch' if 'rolling exceeds' in reason else 'physical gate failure'
        failure=dict(case=name,status='replay_infeasible',optimizer_predicted_feasible=bool(result and result.releasable),
            realized_metrics=None,violation=reason,category=category,diagnostic=diagnostic,retained=True,
            matched_conditions=proof,decision_mutation=False)
        if result and not heat_trace.empty:
            hf=heat_comparison(result,heat_trace)
            failure['completed_attempt_heat_count']=len(hf)
            if len(hf):
                failure['attempt_forecast_errors']=dict(energy=errors(hf.actual_energy_kWh,hf.energy_p50_kWh,hf.energy_p90_kWh),duration=errors(hf.actual_duration_min,hf.duration_p50_min,hf.duration_p90_min))
                if directory:hf.to_parquet(directory/'partial_heat_comparison.parquet',index=False)
        if directory:
            heat_trace.to_parquet(directory/'failed_heat_trace_evaluation_only.parquet',index=False)
            write_json(directory/'failure.json',failure);write_json(directory/'matched_conditions.json',proof)
        return failure,None
    verifier=verify_physics(sim,inp,controls)
    matched=match_manifest(baseline,sim,controls,inp,scenario_proof)
    metrics,ledger=realized_metrics(sim,inp,verifier)
    passed=verifier['feasible'] and matched['status']=='PASS' and matched['opening_inventory_matches']
    entry=dict(case=name,status='physically_valid' if passed else 'replay_infeasible',realized_metrics=metrics,
               verification=verifier,matched_conditions=matched,retained=True,scope=controls.scope)
    if result:
        summary,hf,lf=compare_forecast(sim,inp,result,verifier);entry['forecast_errors']=summary
        # Quantify requested vs realized rolling, even for explicitly partial replay.
        actual=sim.latent_truth[(sim.latent_truth.asset_id=='MAIN')&(sim.latent_truth.timestamp>=pd.Timestamp(controls.origin))&(sim.latent_truth.timestamp<pd.Timestamp(controls.end))]
        entry['rolling_dispatch_max_error_t']=float(abs(actual.rolled_billet_t.to_numpy()-[r['rolling_billet_t'] for r in result.load_trajectory]).max())
        if directory:
            hf.to_parquet(directory/'heat_forecast_comparison.parquet',index=False);lf.to_parquet(directory/'load_forecast_comparison.parquet',index=False)
    if directory:
        sim.write(directory/'simulation');ledger.to_parquet(directory/'realized_tariff_ledger.parquet',index=False)
        write_json(directory/'evaluation.json',entry);write_json(directory/'matched_conditions.json',matched)
    return entry,sim
