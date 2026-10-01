"""Independent report/release assembly. Evaluation labels never return to planning."""
from pathlib import Path
import json,shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from energy_copilot.common import write_json,sha256,canonical_hash,load_config
from energy_copilot.robust.integrity import verify_upstream


def cell(x):return 'unavailable' if x is None else f'{x:.3f}'


def static_execution_audit(config, seed, controls_path, expected):
    """Post-evaluation timing/causality only; never fed back to planning."""
    from energy_copilot.replay.compatible_v111 import simulate,InvariantError
    controls=json.loads(controls_path.read_text());causal={}
    try:
        sim=simulate(config,seed=seed,days=30,schedule=controls['schedule'],practice_by_day={int(k):v for k,v in controls['practice_by_day'].items()},rolling_dispatch={int(k):v for k,v in controls['rolling_dispatch'].items()})
        if expected['status']!='physically_valid':raise RuntimeError('Previously failed static execution unexpectedly succeeded')
        heat=sim.latent_heats
    except InvariantError as exc:
        if expected['status']=='physically_valid' or str(exc)!=expected.get('violation',expected.get('reason')):raise RuntimeError('Static evaluation reproduction mismatch') from exc
        trace=exc.__traceback__;local={}
        while trace:
            if trace.tb_frame.f_code.co_name=='simulate':local=trace.tb_frame.f_locals
            trace=trace.tb_next
        heat=pd.DataFrame(local.get('heatrows',[]))
        prior=heat.iloc[-1] if len(heat) else None
        if prior is not None and prior.heat_id.startswith('D007_') and 'overlapping' in str(exc):
            requested=pd.Timestamp(controls['schedule'][local['heat_id']]);overlap=(pd.Timestamp(prior.end)-requested).total_seconds()/60
            causal=dict(preceding_heat=prior.heat_id,blocked_heat=local['heat_id'],actual_prior_end=pd.Timestamp(prior.end).isoformat(),blocked_requested_start=requested.isoformat(),overlap_min=overlap,prior_physical_faults=prior.fault_label,prior_nonpowered_min=float(prior.nonpowered_min),prior_outage_min=float(prior.outage_min),interpretation='Exact reproduced overlap; physical marks explain contributing terms, not a counterfactual attribution')
    day=heat[heat.heat_id.str.startswith('D007_')].copy() if len(heat) else pd.DataFrame()
    finish=None if expected['status']!='physically_valid' or day.empty else pd.to_datetime(day.end).max()
    return day,finish,causal


def release(draft=False):
    root=Path('replay/robustness_v1')
    if (root/'release_manifest.json').exists():raise RuntimeError('Released artifact immutable; use a successor output version')
    protection=verify_upstream();design=json.loads((root/'design_freeze.json').read_text());split=json.loads((root/'split_manifest.json').read_text())
    protocol=json.loads((root/'final_evaluation_protocol.json').read_text())
    calibration=json.loads((root/'duration_calibration.json').read_text())
    if protocol['design_sha256']!=design['design_sha256'] or any(sha256(p)!=h for p,h in design['source_hashes'].items()):raise RuntimeError('Planning design changed after final-evaluation freeze')
    if design['config_sha256']!=sha256('configs/robustness_v1.yaml') or design['calibration_sha256']!=canonical_hash(calibration) or design['split_sha256']!=canonical_hash(split):raise RuntimeError('Frozen config/calibration/split mismatch')
    if protocol['validation_sha256']!=sha256(root/'validation_comparison.json'):raise RuntimeError('Validation evidence changed after final freeze')
    reproducibility=json.loads((root/'adaptive_reproducibility.json').read_text())
    if reproducibility['status']!='PASS' or not all(reproducibility['checks'].values()):raise RuntimeError('Adaptive reproduction gate failed')
    comparisons={p:json.loads((root/f'{p}_comparison.json').read_text()) for p in ('development','validation','final_regression')}
    rows=json.loads((root/'final_regression_results.json').read_text());failures=[];hist={k:[] for k in ('state','prediction','schedule')};steps=[]
    mechanisms=[];static_heat=[];finish_by_case={};causal_context=[];cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    # Frozen final fault labels are evaluation-only explanations, never inputs.
    for row in rows:
        seed=row['seed'];strategy=row['strategy'];result=row['result'];directory=root/'final_regression'/f'seed_{seed}'/strategy
        if strategy in ('E0','E1','E2') and (directory/'controls.json').exists():
            h,finish,causal=static_execution_audit(cfg,seed,directory/'controls.json',result)
            if len(h):h.insert(0,'seed',seed);h.insert(1,'strategy',strategy);static_heat.append(h)
            if finish is not None:finish_by_case[(seed,strategy)]=finish
            if causal:causal_context.append(dict(seed=seed,strategy=strategy,evaluation_only=True,**causal))
        for name in hist:
            path=directory/f'{name}_history.parquet'
            if path.exists():
                f=pd.read_parquet(path);f.insert(0,'seed',seed);f.insert(1,'strategy',strategy)
                if name=='state':
                    # The last completion terminates the loop without another
                    # solve. Include its archived PUBLIC state in the release
                    # timeline while leaving original controller logs intact.
                    final=json.loads((directory/'controller_result.json').read_text())['final_state']
                    f['record_kind']='replanning_state'
                    if pd.Timestamp(final['current_time'])>pd.to_datetime(f.current_time).max():
                        last=dict(seed=seed,strategy=strategy,step=int(f.step.max())+1,current_time=pd.Timestamp(final['current_time']),inventory_t=final['actual_inventory_t'],completed_heats=len(final['completed_heats']),remaining_heats=len(final['remaining_heats']),bars_t=sum(final['executed_rolling'])*float(cfg['material']['rolling_yield']['value']),record_kind='completed_heat_state')
                        f=pd.concat([f,pd.DataFrame([last])],ignore_index=True)
                hist[name].append(f)
        for p in sorted(directory.glob('replan_step*.json')):
            record=json.loads(p.read_text())
            # Intraday starts need not equal the nanosecond completion origin.
            # Preserve raw logs; expand the already archived selected PUBLIC
            # coefficients into a complete audit record, never actual outcomes.
            record['predictions']=[dict(heat_id=s['heat_id'],practice_mode=s['selected_practice'],energy_p50_kWh=s['energy_p50_kWh'],energy_p90_kWh=s['energy_p90_kWh'],duration_p50_min=s['duration_p50_min'],duration_p90_min=s['duration_p90_min'],available_at=record['current_time'],model_version=record['prediction_version']) for s in record['selected_schedule']]
            steps.append(dict(seed=seed,strategy=strategy,source_path=str(p).replace('\\','/'),source_sha256=sha256(p),prediction_audit_method='selected archived PredictionService coefficients; no target/truth values',**record))
        if result['status']!='physically_valid':
            failures.append(dict(seed=seed,strategy=strategy,status=result['status'],cause=result.get('failure_class'),reason=result.get('reason',result.get('violation')),retained=True))
            latent=pd.read_parquet(Path('replay/optimizer_v1/evaluation')/f'seed_{seed}'/'baseline/simulation/latent_heats.parquet')
            day=latent[latent.heat_id.str.startswith('D007_')]
            diagnostic=result.get('diagnostic',{});offending=diagnostic.get('heat_id')
            for h in day.itertuples():
                if h.fault_label:
                    mechanisms.append(dict(seed=seed,strategy=strategy,heat_id=h.heat_id,physical_faults=h.fault_label,
                        nonpowered_min=h.nonpowered_min,outage_min=h.outage_min,
                        is_reported_failing_heat=(h.heat_id==offending),
                        interpretation='Matched exogenous mechanism present; not every listed mark is proven causal. Baseline absolute duration includes normal practice; replay uses loss-40.',evaluation_only=True))
    pd.DataFrame(failures).to_parquet(root/'failure_analysis.parquet',index=False)
    pd.DataFrame(mechanisms).to_parquet(root/'failure_mechanisms_evaluation_only.parquet',index=False)
    pd.DataFrame(causal_context).to_parquet(root/'failure_causal_context_evaluation_only.parquet',index=False)
    if static_heat:pd.concat(static_heat,ignore_index=True).to_parquet(root/'static_heat_execution_evaluation_only.parquet',index=False)
    for name,frames in hist.items():
        if frames:pd.concat(frames,ignore_index=True).to_parquet(root/f'{name}_history.parquet',index=False)
    write_json(root/'each_replan_step.json',steps);write_json(root/'replay_results.json',rows)
    write_json(root/'initial_plan.json',dict(version='robustness_v1',plans=[dict(seed=r['seed'],strategy=r['strategy'],path=f'final_regression/seed_{r["seed"]}/{r["strategy"]}/initial_plan.json') for r in rows]))
    paired={}
    for strategy in ('E0','E1','E2','E3','E4'):
        values_=[]
        for row in rows:
            if row['strategy']!=strategy or row['result']['status']!='physically_valid':continue
            base=json.loads((root/'final_regression'/f'seed_{row["seed"]}'/'reference_same_practice.json').read_text())['realized_metrics'];m=row['result']['realized_metrics']
            values_.append(dict(seed=row['seed'],energy_delta_kWh=m['total_kWh']-base['total_kWh'],
                               synthetic_cost_delta_Rs=m['physical_evaluation_tariff_cost_Rs']-base['physical_evaluation_tariff_cost_Rs'],
                               synthetic_tariff_reduction_pct=100*(base['physical_evaluation_tariff_cost_Rs']-m['physical_evaluation_tariff_cost_Rs'])/base['physical_evaluation_tariff_cost_Rs']))
        paired[strategy]=values_
    write_json(root/'matched_reference_attribution.json',paired)
    matched_strategies={}
    for alternative in ('E0','E1','E2','E3'):
        comparisons_=[]
        for seed in split['final_regression']:
            a=next(r['result'] for r in rows if r['seed']==seed and r['strategy']==alternative)
            b=next(r['result'] for r in rows if r['seed']==seed and r['strategy']=='E4')
            if a['status']!='physically_valid' or b['status']!='physically_valid':continue
            ma,mb=a['realized_metrics'],b['realized_metrics']
            comparisons_.append(dict(seed=seed,energy_delta_kWh=mb['total_kWh']-ma['total_kWh'],synthetic_cost_delta_Rs=mb['physical_evaluation_tariff_cost_Rs']-ma['physical_evaluation_tariff_cost_Rs'],synthetic_cost_delta_pct=100*(mb['physical_evaluation_tariff_cost_Rs']/ma['physical_evaluation_tariff_cost_Rs']-1)))
        matched_strategies[alternative]=dict(comparison='E4 minus alternative; paired physically feasible seeds only',n=len(comparisons_),pairs=comparisons_,mean_energy_delta_kWh=None if not comparisons_ else float(np.mean([x['energy_delta_kWh'] for x in comparisons_])),mean_synthetic_cost_delta_pct=None if not comparisons_ else float(np.mean([x['synthetic_cost_delta_pct'] for x in comparisons_])))
    write_json(root/'matched_strategy_attribution.json',matched_strategies)
    supplemental={}
    for strategy in ('E0','E1','E2','E3','E4'):
        selected=[r for r in rows if r['strategy']==strategy];valid=[r for r in selected if r['result']['status']=='physically_valid'];forecast=[];reserve=[];finish=[];actual_reserve=[]
        for r in selected:
            folder=root/'final_regression'/f'seed_{r["seed"]}'/strategy;entry=r['result']
            if 'forecast_errors' in entry:forecast.append(entry['forecast_errors']['heat_duration'])
            elif 'attempt_forecast_errors' in entry:forecast.append(entry['attempt_forecast_errors']['duration'])
            if (folder/'controller_result.json').exists():
                control=json.loads((folder/'controller_result.json').read_text());pub=pd.DataFrame(control['final_state']['frozen_executed_decisions'])
                predictions=pd.read_parquet(folder/'prediction_history.parquet')
                if len(pub) and len(predictions):
                    j=predictions.merge(pub,on='heat_id',suffixes=('_pred','_actual'));actual=(pd.to_datetime(j.end)-pd.to_datetime(j.start_actual)).dt.total_seconds()/60
                    error=actual-j.duration_p50_min
                    forecast.append(dict(n=len(j),MAE=float(error.abs().mean()),bias_actual_minus_p50=float(error.mean()),p90_exceedance=float((actual>j.duration_p90_min).mean())))
            if (folder/'initial_plan.json').exists():
                p=json.loads((folder/'initial_plan.json').read_text());schedule=p.get('selected_schedule',p.get('schedule',[]))
                if schedule:reserve.append(float((pd.Timestamp('2026-01-13T00:00:00')-pd.Timestamp(schedule[-1]['predicted_end'])).total_seconds()/60))
            margin=entry.get('actual_end_margin_min')
            if margin is None and (r['seed'],strategy) in finish_by_case:margin=float((pd.Timestamp('2026-01-13')-finish_by_case[(r['seed'],strategy)]).total_seconds()/60)
            if entry['status']=='physically_valid' and margin is not None:
                actual_reserve.append(margin)
                if (folder/'initial_plan.json').exists() and schedule:
                    finish.append(float((pd.Timestamp('2026-01-13')-pd.Timedelta(minutes=margin)-pd.Timestamp(schedule[-1]['predicted_end'])).total_seconds()/60))
        def distribution(key):
            x=np.array([r['result']['realized_metrics'][key] for r in valid],dtype=float)
            return dict(n=len(x),mean=None if not len(x) else float(x.mean()),p10=None if not len(x) else float(np.quantile(x,.1)),p50=None if not len(x) else float(np.median(x)),p90=None if not len(x) else float(np.quantile(x,.9)))
        n=sum(f['n'] for f in forecast)
        supplemental[strategy]=dict(attempted=len(selected),overlap_failures=sum(r['result'].get('failure_class')=='duration_miss_overlap' for r in selected),end_of_day_failures=sum(r['result'].get('failure_class')=='end_of_day_overrun' for r in selected),
            conditional_on_feasible={k:distribution(k) for k in ('total_kWh','IF_SEC_kWh_per_t','peak_piecewise_kVA','bar_t','final_inventory_t','inventory_min_t','inventory_max_t','IF_idle_hours','IF_utilization')},
            completed_observed_heat_prediction_metrics=dict(n=n,MAE=None if not n else sum(f['MAE']*f['n'] for f in forecast)/n,bias=None if not n else sum(f['bias_actual_minus_p50']*f['n'] for f in forecast)/n,p90_exceedance=None if not n else sum(f['p90_exceedance']*f['n'] for f in forecast)/n,p95_exceedance=None,p95_limitation='Frozen PredictionService supplies p90, not an individual-outcome p95'),
            mean_actual_end_reserve_min=None if not actual_reserve else float(np.mean(actual_reserve)),mean_realized_minus_initial_predicted_finish_min=None if not finish else float(np.mean(finish)),
            mean_nominal_initial_end_reserve_min=None if not reserve else float(np.mean(reserve)),reserve_note='Nominal p50 plan margin; declared minimum applies independently to every required scenario.')
    write_json(root/'operational_prediction_metrics.json',supplemental)
    regressions={str(seed):json.loads((root/'final_regression'/f'seed_{seed}'/'E0_regression.json').read_text()) for seed in split['final_regression']}
    if not all(all(all(c.values()) for c in s.values()) for s in regressions.values()):raise RuntimeError('E0 regression not satisfied')
    write_json(root/'E0_final_regression.json',regressions)
    table=['| strategy | development valid/attempted | validation valid/attempted | final valid/attempted | final conditional kWh | final conditional synthetic Rs | replans |',
           '| --- | --- | --- | --- | --- | --- | --- |']
    for s in ('E0','E1','E2','E3','E4'):
        d,v,f=[comparisons[p][s] for p in ('development','validation','final_regression')]
        table.append(f'| {s} | {d["feasible"]}/{d["attempted"]} | {v["feasible"]}/{v["attempted"]} | {f["feasible"]}/{f["attempted"]} | {cell(f["conditional_on_feasible"]["total_kWh"]["mean"])} | {cell(f["conditional_on_feasible"]["physical_evaluation_tariff_cost_Rs"]["mean"])} | {f["total_replans"]} |')
    tab='\n'.join(table);policy=design['policy'];cal=json.loads((root/'duration_calibration.json').read_text())
    tests=json.loads((root/'tests.json').read_text());resource=json.loads((root/'resource_failures.json').read_text())
    if tests['exit_code']!=0 or tests['passed']<229:raise RuntimeError('Full implementation and final acceptance tests required before release')
    e4=comparisons['final_regression']['E4'];m4=e4['conditional_on_feasible'];op=supplemental['E4']
    effects='; '.join(f"E4 versus {s}: {m['n']} paired feasible seeds, mean cost delta {cell(m['mean_synthetic_cost_delta_pct'])}% and mean energy delta {cell(m['mean_energy_delta_kWh'])} kWh" for s,m in matched_strategies.items())
    quantitative=f"Final E4: {e4['feasible']}/{e4['attempted']} physical passes, {e4['total_replans']} replans, mean {cell(m4['total_kWh']['mean'])} kWh/day, IF SEC {cell(m4['IF_SEC_kWh_per_t']['mean'])} kWh/t, plant intensity {cell(m4['plant_kWh_per_t_bars']['mean'])} kWh/t, synthetic cost {cell(m4['physical_evaluation_tariff_cost_Rs']['mean'])} Rs/day. Mean observed duration MAE {cell(op['completed_observed_heat_prediction_metrics']['MAE'])} min, bias {cell(op['completed_observed_heat_prediction_metrics']['bias'])} min, p90 exceedance {cell(op['completed_observed_heat_prediction_metrics']['p90_exceedance'])}, realized end reserve {cell(op['mean_actual_end_reserve_min'])} min, realized-minus-initial finish {cell(op['mean_realized_minus_initial_predicted_finish_min'])} min. Absolute feasibility improvement over E0 is {100*e4['absolute_feasibility_improvement']:.1f} percentage points; relative improvement is undefined with zero E0 passes. {effects}. These are conditional comparisons; failed cases remain in the feasibility denominator and cannot supply a complete-day cost.\n\n"
    front='All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.\n\nE0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.\n\n'
    summary=front+f'''Frozen upstream integrity: {protection}. E0 seed-42 four-case metrics/status match exactly; every 201–210 normal/synthetic central/conservative outcome also matches frozen Phase II-D. No frozen upstream file was changed.

Fresh development: {split['development']}; validation: {split['validation']}; final regression: {split['final_regression']}. All policy calibration uses only six fresh development days. Policy selection preceded validation; the final protocol records design/config/source and completed-validation hashes before final regression. Final outcomes never select parameters. No predictive model or simulator calibration changed.

{tab}

Architecture: frozen PredictionService → shared-decision scenario MILP → commit one heat and rolling commands as slots begin → unchanged-physics execution prefix → publish completed heat/closed readings → remaining-horizon MILP. Every completed operational trace is independently replayed through frozen replay/compatible_v111.py with matched full30-day conditions and all physical checks. Incomplete/failed plans remain unreleasable.

Policy: {policy}. Five-minute candidate discretization left fewer than five reserve minutes under the selected scenario envelope. The successor uses one-minute heat-start resolution, retaining the fixed quarter-hour plant/accounting clock. On development, a five-minute reserve cost about 0.3975% more than zero; larger reserves and extra uncertainty buffers were not selected. This is a combined scenario/grid/reserve/adaptive policy comparison, not a causal claim that buffering alone produced the change.

Tests: {tests}. Three initial concurrent development solves exhausted host memory; their partial plans/logs/failure records remain under development_resource_failures/. Later solves use a deterministic 1000-node serial budget and at most two experiment workers. A checked feasible incumbent is not labelled optimal unless HiGHS proves optimality.

Artifacts: replay/robustness_v1 includes initial and each-step plans, state/prediction/schedule histories, replay results, every failure, comparisons, matched-reference attribution, design/source/config/split hashes and this release manifest. No LLM, model retraining, automatic maintenance, tariff alteration or online weight learning is present.
'''
    summary+=quantitative
    summary+='\nCreated files: src/energy_copilot/robust/ (contracts, scenario construction, robust MILP, independent remaining/scenario checkers, state projection, controller, evaluation and integrity gates); scripts/phase2e.py and phase2e_release.py; robustness_v1/split/schema and upstream-protection configs; test_robust_scheduling.py and test_robust_release.py; usage/changelog/diff documents; five phase2e reports, comparison plot and replay/robustness_v1 release. Existing upstream source/artifact files were not edited.\n\nLimitations: six development and four validation runs, one matched calendar working day per seed, and ten final seeds; no rare-event safety certification. Fixed reference physics retains algebraic thermal behavior and calendar-based degradation. AUX cannot be refreshed intraday through the frozen API. Availability remains the externally declared calendar; health probabilities do not automatically create availability changes. Day-7 experiments do not validate maintenance/outage scheduling. Alternative triggers, multi-heat/fixed-time commitments and online residual correction remain optional extensions. The one-minute planning grid is part of the successor policy, so reserve/scenario/replanning effects are not individually isolated. Node-limited incumbents may have an optimality gap. The loss-40 practice remains synthetic.\n'
    Path('reports/phase2e_summary.md').write_text('# Phase II-E robust and adaptive scheduling\n\n'+summary,encoding='utf-8')
    robust=front+tab+f'''

Scenario set: central; frozen marginal p90 energy/duration/AUX; two complete development residual-day vectors (median/high-total); one next-heat development positive-residual-p95 stress ({cal['positive_residual_p95_min']:.4f} min). Residuals are relative to p50; max(p90, p50+residual) avoids adding a residual twice. Negative residuals do not shorten nominal occupancy. Energy-duration consistency retains configured full-power/nonpowered lower bounds. No scenario probability or joint safety guarantee is asserted. Whole-day vectors retain dependence/order; pooled adjacent residual correlation is {cal['pooled_adjacent_heat_residual_correlation']:.4f}, based on only six days. The largest observed residual (~14 min) is represented in a whole-day vector; the p95 next-heat stress alone does not cover every half-power event at every position.

Binary heat-start decisions and rolling feed are shared across all required scenarios. Each scenario has independent inventory state; non-overlap, buffers, end reserve, windows, cooling and additive kVA demand bounds remain hard. Scenario energy shapes reserve a rated-power tail. Inventory posts casts at quarter-hour boundaries, uses opening stock only, and bounds stock before consumption. Feasibility solve precedes electricity-cost minimization. Quantiles remain empirical, not physical guarantees. Explicit buffer support is max(minimum, fraction*(p90-p50)); selected additional fraction is zero because scenario occupancy already reserves upper durations. Candidate policy trade-offs, including failed five-minute-grid trials, are retained.

Feasibility denominators include every declared seed, including failures. Conditional cost/energy statistics describe only feasible executions. Absolute improvement is final E4 rate minus E0 rate; relative improvement is undefined when E0 rate is zero. Matched-reference attribution compares the same loss-40 intervention to back-to-back reference operation. Common practice energy reduction must not be attributed to robustness.

All-attempt machine-readable metrics are in final_regression_comparison.json. Initial host-resource aborts are separately recorded; they are not physical passes and no historical failure is erased. The canonical final experiment has one attempt per strategy/seed, plus retained development resource attempts.
'''
    Path('reports/phase2e_robustness_report.md').write_text('# Robustness and cost trade-off\n\n'+robust+'\n'+quantitative,encoding='utf-8')
    adaptive=front+'''Trigger: immediately after each completed heat. Commitment: current heat cannot move; rolling feed is immutable once its quarter-hour slot begins. State uses completed heat billet weights and accepted feed acknowledgements, not latent yard truth. Completed outcomes update legitimate prior-heat history; frozen heat/health models are called again. The frozen AUX API supports midnight origins only, so its published day-ahead forecast is retained without pretending it was refreshed.

For a completion inside a quarter hour, decision_time is the actual posted completion; accounting_geometry_start is the beginning of the current quarter hour. Current-slot feed is fixed; the just-completed billet arrival is a known constant at that slot's close. The opening inventory is reconstructed from that acknowledgement ledger. All new heat starts must be at/after decision_time; one-minute rounding adds at most one minute. Heat log outcomes are immediately available; meter observations are usable only after interval_end. No open interval is posted early.

The remaining-work objective excludes completed IF electricity. Already committed current-slot service energy is a constant and cannot affect decisions. Full-day energy, production, cost, peak demand and stock come only from independent complete replay. Every step records timestamps, public feature values/posting times, prediction version, uncertainty set, remaining heats, chosen plan, constraints and trigger. Replanning does not retrain weights or tune a policy online. No online residual correction was necessary.

Early development quarter-boundary waiting controllers failed after 12 heats; those smoke attempts are retained. Waiting created avoidable cumulative latency. The successor immediate-posting contract removes that wait while preserving the sensor availability boundary.
'''+tab+'\n'
    Path('reports/phase2e_receding_horizon_report.md').write_text('# Receding-horizon execution\n\n'+adaptive,encoding='utf-8')
    failure_text=front+'Every failed final attempt remains in failure_analysis.parquet. No infeasible schedule is represented as feasible; failed complete-day cost/energy is unavailable.\n\n'
    if failures:
        failure_text+='| seed | strategy | status | cause | reason |\n| --- | --- | --- | --- | --- |\n'
        failure_text+='\n'.join('| '+ ' | '.join(str(r[k]).replace('|','/') for k in ('seed','strategy','status','cause','reason'))+' |' for r in failures)+'\n\n'
    failure_text+='failure_mechanisms_evaluation_only.parquet lists matched exogenous physical marks, including half-power, charge/lid/superheat extensions, and outages where present. static_heat_execution_evaluation_only.parquet reproduces exact unchanged controls, including partial failed traces. failure_causal_context_evaluation_only.parquet identifies the preceding heat, its actual end, blocked next start, exact overlap duration and physical contributing marks for every static overlap. These are post-experiment evaluation labels. A mark present somewhere in a day is not itself proof that it caused the failure. Overlap/end-of-day failures are traced to duration misses; no-feasible continuations retain their actual past state and forecast histories. All successful traces independently pass mass/electricity/fuel, demand, cooling, production, inventory, windows/capacity and exact-command checks. Calendar day 7 has no maintenance-outage robustness evidence; later failure-day scheduling is outside this release.\n'
    failure_text+=f'\nFinal failure counts: {len(causal_context)} exact static overlaps, four central adaptive solver-infeasible continuations after 12 completed heats, and one central adaptive end-of-day overrun. Reproduced static overlaps range from {min(x["overlap_min"] for x in causal_context):.3f} to {max(x["overlap_min"] for x in causal_context):.3f} minutes. No E4 final attempt failed. These counts are descriptive evaluation results, not policy selection criteria.\n'
    Path('reports/phase2e_failure_analysis.md').write_text('# Remaining failures\n\n'+failure_text,encoding='utf-8')
    boundary=front+'''PASS: immutable upstream hash manifest; disjoint development/validation/final split; calibration function refuses non-development seeds; frozen policy/config/core source hashes before final evaluation. Source training/calibration code never reads 201–210 outcomes. Frozen Phase II-B artifacts are unchanged.

PASS: public_snapshot projects an explicit sensor/heat allowlist before state/prediction creation; drops fault_label, events, latent truth, health/severity/future failures. Slots require interval_start+15min <= current_time. Completed heat logs require end <= current_time. Past-only heat summaries and condition features retain per-feature posting timestamps. PredictionService independently rejects schema/time violations and unsafe fallbacks. Current-slot material arrival is a completed public billet register, not an unknown future cast.

PASS: typed remaining input validates model/schema, quantile order, calendar/tariff identity, physical parameters, actual inventory and unchanged full production order. Completed records are deeply immutable dataclasses; already executed feed cannot change. Independent checker includes current-slot known arrivals and fixed feed. Tests poison hidden columns and reject future arrivals/predictions and lowered orders.

Evaluation-only: physical twin truth/fault marks are accessible only to replay/checking/report modules, never to feature/context construction. The execution gateway generates the full random tape before decisions but hands the controller filtered public snapshots. Same-seed prefix/default output equivalence is tested. Node-limited optimality and fixed calendar/accelerated degradation are limitations; empirical scenarios are not certified joint safety bounds.
'''
    Path('reports/phase2e_information_boundary.md').write_text('# Information and immutability audit\n\n'+boundary,encoding='utf-8')
    shutil.copyfile('configs/robustness_v1.yaml',root/'config_snapshot.yaml');shutil.copyfile('requirements-phase2c.lock.txt',root/'requirements.lock.txt')
    shutil.copyfile('data/processed/sim_v1.1/config_snapshot.yaml',root/'plant_config_snapshot.yaml')
    shutil.copyfile('configs/optimizer_v1.yaml',root/'optimizer_config_snapshot.yaml')
    shutil.copyfile('models/phase2b_v1/prediction_contract.json',root/'prediction_contract_snapshot.json')
    shutil.copyfile('configs/robustness_schema_v1.yaml',root/'schema_snapshot.yaml')
    (root/'data_card.md').write_text('# Robustness v1 data card\n\n'+summary+'\nPublic histories and prediction tables exclude physical fault labels/truth. failure_mechanisms_evaluation_only.parquet and physical replay metrics are evaluation artifacts, never downstream predictors.\n',encoding='utf-8')
    reportdir=Path('reports/phase2e');reportdir.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    x=np.arange(5);names=['E0','E1','E2','E3','E4']
    for j,p in enumerate(('development','validation','final_regression')):
        axes[0].bar(x+(j-1)*.25,[comparisons[p][s]['feasibility_rate'] for s in names],width=.25,label=p)
    axes[0].set(xticks=x,xticklabels=names,ylim=(0,1.1),ylabel='Feasible fraction (all declared seeds)');axes[0].legend(fontsize=7)
    axes[1].bar(x,[comparisons['final_regression'][s]['conditional_on_feasible']['physical_evaluation_tariff_cost_Rs']['mean'] or 0 for s in names])
    axes[1].set(xticks=x,xticklabels=names,ylabel='Synthetic Rs; feasible executions only')
    for i,s in enumerate(names):
        if not comparisons['final_regression'][s]['feasible']:axes[1].text(i,0,'no valid\nexecution',ha='center')
    fig.tight_layout();fig.savefig(reportdir/'feasibility_cost.png',dpi=150);plt.close(fig)
    reports={str(p).replace('\\','/'):sha256(p) for p in Path('reports').glob('phase2e*.md')}
    reports.update({str(p).replace('\\','/'):sha256(p) for p in reportdir.glob('*.png')})
    code={str(p).replace('\\','/'):sha256(p) for p in [*Path('src/energy_copilot/robust').glob('*.py'),Path('scripts/phase2e.py'),Path('scripts/phase2e_release.py'),Path('tests/test_robust_scheduling.py'),Path('tests/test_robust_release.py'),Path('configs/robustness_v1.yaml'),Path('configs/robustness_schema_v1.yaml'),Path('configs/robustness_split_v1.json'),Path('configs/phase2e_readonly_manifest.json'),Path('docs/phase2e_execution_prefix_diff.patch'),Path('docs/phase2e_remaining_checker_diff.patch'),Path('docs/phase2e_usage.md'),Path('docs/phase2e_changelog.md')]}
    write_json(root/'code_manifest.json',code)
    hashes={str(p.relative_to(root)).replace('\\','/'):sha256(p) for p in root.rglob('*') if p.is_file() and p.name!='release_manifest.json'}
    if not draft:write_json(root/'release_manifest.json',dict(version='robustness_v1',hashes=hashes,reports=reports,code=code,upstream=protection,design=design,tests=tests))
    print('Draft verified' if draft else 'Released robustness_v1; upstream unchanged',protection,flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--draft',action='store_true')
    release(draft=parser.parse_args().draft)
