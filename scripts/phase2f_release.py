"""Verify complete Phase II-F evidence, then write reports and immutable hashes."""
from pathlib import Path
import json,re
import pandas as pd
from energy_copilot.common import sha256,write_json,load_config,values
from energy_copilot.maintenance.contracts import MaintenanceAction
from energy_copilot.maintenance.scenario import scenario as maintenance_scenario
from scripts.phase2f import ROOT,split,guard,frozen_policy


def load(partition):
    path=ROOT/f'{partition}_comparison.json'
    if not path.is_file():raise RuntimeError('Incomplete partition '+partition)
    return json.loads(path.read_text())


def observed_failure_prefix(root,strategy):
    folder=root/('F0' if strategy=='F1' else strategy)
    control=json.loads((folder/'controller_result.json').read_text())
    executed=control['final_state']['frozen_executed_decisions']
    predictions={row['heat_id']:row['duration_p50_min'] for row in pd.read_parquet(folder/'prediction_history.parquet').to_dict('records')}
    errors=[]
    for heat in executed:
        if heat['heat_id'] in predictions:
            actual=(pd.Timestamp(heat['end'])-pd.Timestamp(heat['start'])).total_seconds()/60
            errors.append(actual-float(predictions[heat['heat_id']]))
    return dict(completed_heats=control['completed_heats'],remaining_heats=len(control['final_state']['remaining_heats']),
        last_public_state_time=control['final_state']['current_time'],
        completed_duration_bias_min=None if not errors else sum(errors)/len(errors),
        completed_positive_duration_error_min=sum(max(0,e) for e in errors),
        observed_prefix_only=True,full_day_independently_accepted=False)


def count_case_evidence(partition,seeds,days):
    for seed in seeds:
        for day in days:
            root=ROOT/partition/f'seed_{seed}_day_{day}'
            if not (root/'attempt_results.json').is_file():raise RuntimeError('Missing attempted case '+str(root))
            rows=json.loads((root/'attempt_results.json').read_text())
            if [r['strategy'] for r in rows]!=['F0','F1','F2']:raise RuntimeError('Strategy omission '+str(root))
            f0,f1,f2=[r['result'] for r in rows]
            if f0['status']!=f1['status'] or f0['realized_metrics']!=f1['realized_metrics'] or not f1.get('advisory_only'):
                raise RuntimeError('F1 advice changed no-action physics '+str(root))
            published=pd.read_parquet(root/'F0'/'health_prediction_history.parquet')
            published.loc[published.warning.eq(True)].to_parquet(root/'F1'/'advisory_log.parquet',index=False)
            decisions=pd.read_parquet(root/'F2'/'maintenance_decisions.parquet')
            attribution=pd.read_parquet(root/'maintenance_attribution.parquet')
            if len(decisions):
                lookup={(r.asset_id,str(r.service_start)):r.classification for r in attribution.itertuples()}
                decisions['final_replay_outcome']=[lookup.get((r.asset_id,str(r.start_time)),'undetermined_counterfactual') for r in decisions.itertuples()]
                decisions['final_replay_status']=f2['status']
            decisions['evaluation_only']=True
            decisions.to_parquet(root/'F2'/'maintenance_decision_outcomes.parquet',index=False)
            # A rolling-horizon recommendation can be replaced before commitment.
            # Preserve its disposition instead of counting every selected window
            # as a completed preventive intervention.
            recommendation_rows=[]
            plans=[root/'F2'/'initial_plan.json',*sorted((root/'F2').glob('replan_step_*.json'))]
            for path in plans:
                record=json.loads(path.read_text())
                for action in record.get('selected_maintenance',()):
                    asset=action['asset_id'];start=action['start_time']
                    posted=next(r for r in record['health_audit'] if r['asset_id']==asset)
                    match=decisions.loc[decisions.asset_id.eq(asset)&decisions.start_time.eq(start)] if len(decisions) else decisions
                    committed_here=bool(len(match) and (pd.to_datetime(match.decision_time,format='mixed')==pd.Timestamp(record['current_time'])).any())
                    # Terminal recommendation dispositions, not a count of plan appearances.
                    acknowledged=bool(committed_here and bool(match.executed.iloc[0]))
                    disposition=('executed' if acknowledged else 'replaced_by_replan' if len(match) else
                                 'run_aborted_before_execution' if f2['status']!='physically_valid' else 'cancelled')
                    recommendation_rows.append(dict(step=record['step'],decision_time=record['current_time'],
                        asset_id=asset,start_time=start,duration_min=action['duration_min'],
                        calibrated_probability=posted['calibrated_probability'],policy_threshold=posted['threshold'],
                        model_version=posted['model_version'],public_health_evidence=posted['visible_evidence'],
                        alternative_windows=[r['start_time'] for r in record['maintenance_candidates'] if r['asset_id']==asset],
                        binding_constraints=record['binding_constraints'],disposition=disposition,
                        eligible=bool(posted['eligible']),committed=committed_here,
                        execution_acknowledged=acknowledged,full_day_verified=f2['status']=='physically_valid' and acknowledged,
                        final_replay_status=f2['status'],final_service_attribution=(None if not committed_here else match.final_replay_outcome.iloc[0]),
                        evaluation_only=True))
            pd.DataFrame(recommendation_rows).to_parquet(root/'F2'/'maintenance_recommendation_history.parquet',index=False)
            if len(recommendation_rows)!=f2.get('maintenance_recommendations',0):
                raise RuntimeError('Recommendation ledger mismatch '+str(root))
            write_json(root/'maintenance_attribution.json',attribution.to_dict('records'))
            failures=[dict(strategy=key,status=result['status'],cause=result.get('failure_class'),reason=result.get('reason'),retained=True,
                           **observed_failure_prefix(root,key))
                      for key,result in (('F0',f0),('F1',f1),('F2',f2)) if result['status']!='physically_valid']
            pd.DataFrame(failures).to_parquet(root/'failure_analysis.parquet',index=False)
            warning_leads=[]
            for event in f0.get('failure_events_day',()):
                at=pd.Timestamp(event['start'])
                history=published.loc[published.asset_id.eq(event['asset_id'])&published.warning.eq(True)]
                history=history.loc[(pd.to_datetime(history.available_at,format='mixed')<=at)&
                                    (pd.to_datetime(history.available_at,format='mixed')>=at-pd.Timedelta(hours=24))]
                warning_leads.append(dict(asset_id=event['asset_id'],failure_time=event['start'],
                    warning_lead_min=None if history.empty else float((at-pd.to_datetime(history.available_at,format='mixed').min()).total_seconds()/60)))
            a=f0.get('realized_metrics');b=f2.get('realized_metrics')
            paired=None if f0['status']!='physically_valid' or f2['status']!='physically_valid' else dict(
                delta_total_kWh=b['total_kWh']-a['total_kWh'],
                delta_IF_SEC_kWh_per_t=b['IF_SEC_kWh_per_t']-a['IF_SEC_kWh_per_t'],
                delta_synthetic_tariff_Rs=b['physical_evaluation_tariff_cost_Rs']-a['physical_evaluation_tariff_cost_Rs'],
                delta_bars_t=b['bar_t']-a['bar_t'],
                delta_inventory_min_t=b['inventory_min_t']-a['inventory_min_t'],
                delta_inventory_final_t=b['final_inventory_t']-a['final_inventory_t'],
                delta_corrective_downtime_hours=sum(b['downtime_hours'].values())-sum(a['downtime_hours'].values()),
                preventive_service_hours=f2.get('maintenance_executed',0)*.25)
            write_json(root/'matched_comparison.json',dict(seed=seed,day=day,
               F0_status=f0['status'],F1_status=f1['status'],F2_status=f2['status'],
               F0_failures=f0.get('failure_events_day',[]),F2_failures=f2.get('failure_events_day',[]),
               F0_corrective_downtime_hours=None if a is None else a['downtime_hours'],
               F2_corrective_downtime_hours=None if b is None else b['downtime_hours'],
               F2_preventive_services=f2.get('maintenance_executed',0),
               F0_warning_lead_times=warning_leads,
               F0_replans=f0['replans'],F2_replans=f2['replans'],
               F0_exogenous_sha256=f0.get('matched_conditions',{}).get('original_exogenous_sha256'),
               F2_exogenous_sha256=f2.get('matched_conditions',{}).get('replay_exogenous_sha256'),
               both_physically_valid=paired is not None,paired_physical_deltas=paired,
               interpretation='SYNTHETIC-MAINTENANCE matched replay; no field maintenance or billing claim'))
            for strategy in ('F0','F2'):
                folder=root/strategy
                for name in ('initial_plan.json','controller_result.json','state_history.parquet','prediction_history.parquet',
                             'schedule_history.parquet','health_prediction_history.parquet','maintenance_candidate_history.parquet',
                             'maintenance_decisions.parquet','replay_results.json'):
                    if not (folder/name).is_file():raise RuntimeError('Missing controller evidence '+str(folder/name))
                health=pd.read_parquet(folder/'health_prediction_history.parquet')
                if not health.empty and (pd.to_datetime(health.available_at,format='mixed')>pd.to_datetime(health.decision_time,format='mixed')).any():
                    raise RuntimeError('Future health publication in '+str(folder))
                if any(any(marker in col.lower() for marker in ('latent','fault_severity','future_failure','noise_tape')) for col in health.columns):
                    raise RuntimeError('Hidden health field in '+str(folder))
                entry=json.loads((folder/'replay_results.json').read_text())
                if entry['status']=='physically_valid':
                    if entry['verification']['violations'] or not entry['matched_conditions']['history_prefix_identical'] or \
                       entry['matched_conditions']['original_exogenous_sha256']!=entry['matched_conditions']['replay_exogenous_sha256']:
                        raise RuntimeError('Unverified physical replay '+str(folder))


def fault_process(split_manifest):
    """Evaluation-only fault occurrence across all attempted scenarios."""
    plant=values(load_config('data/processed/sim_v1.1/config_snapshot.yaml'))
    rows=[];summary={}
    for part in ('development','validation','final'):
        for seed in split_manifest[part]:
            base=maintenance_scenario(plant,seed,30)
            for day in split_manifest['calendar_days']:
                root=ROOT/part/f'seed_{seed}_day_{day}'
                actions=tuple(MaintenanceAction(**a) for a in json.loads((root/'F2'/'controller_result.json').read_text())['maintenance_actions'])
                try:maintained=maintenance_scenario(plant,seed,30,actions);error=None
                except ValueError as exc:maintained=None;error=str(exc)
                lo=day*1440;hi=lo+1440
                for strategy,tape in (('F0',base),('F2',maintained)):
                    events=[] if tape is None else [e for e in tape['events'] if e['type']=='failure' and lo<=e['start_min']<hi and e['asset_id'] in ('MILL_01','PMP_01')]
                    rows.append(dict(split=part,seed=seed,day=day,strategy=strategy,tape_valid=tape is not None,
                         tape_error=error if strategy=='F2' else None,failure_occurrence=bool(events),fault_count=len(events),
                         mill_fault_count=sum(e['asset_id']=='MILL_01' for e in events),pump_fault_count=sum(e['asset_id']=='PMP_01' for e in events),
                         corrective_repair_hours=sum((e['end_min']-e['start_min'])/60 for e in events),
                         source='Evaluation-only calendar-age fault tape; no optimizer access and not physical schedule acceptance'))
        summary[part]={}
        for strategy in ('F0','F2'):
            selected=[r for r in rows if r['split']==part and r['strategy']==strategy];valid=[r for r in selected if r['tape_valid']]
            summary[part][strategy]=dict(attempted=len(selected),tape_valid=len(valid),
                failure_occurrence_rate=None if not valid else sum(r['failure_occurrence'] for r in valid)/len(valid),
                fault_count=sum(r['fault_count'] for r in valid),
                corrective_repair_hours=sum(r['corrective_repair_hours'] for r in valid),
                limitation='Evaluation-only fault process; failed operating plans remain infeasible')
    pd.DataFrame(rows).to_parquet(ROOT/'fault_process_comparison.parquet',index=False)
    write_json(ROOT/'fault_process_comparison.json',summary)
    return summary


def main():
    if (ROOT/'release_manifest.json').exists():raise RuntimeError('Phase II-F release is already frozen')
    protected=guard();s=split();policy=frozen_policy()
    comparison={p:load(p) for p in ('development','validation','final')}
    for p in comparison:count_case_evidence(p,s[p],s['calendar_days'])
    fault_summary=fault_process(s)
    final_case_metrics={};warning_leads=[];recommendations=0;service_minutes=0;accepted_services=0
    for strategy in ('F0','F2'):
        selected=[]
        for seed in s['final']:
            for day in s['calendar_days']:
                root=ROOT/'final'/f'seed_{seed}_day_{day}'
                result=json.loads((root/strategy/'replay_results.json').read_text())
                if strategy=='F2':
                    recommendations+=result.get('maintenance_recommendations',0)
                    service_minutes+=sum(action['duration_min'] for action in result.get('maintenance_actions',()))
                    if result['status']=='physically_valid':accepted_services+=result.get('maintenance_executed',0)
                if strategy=='F0':
                    paired=json.loads((root/'matched_comparison.json').read_text())
                    warning_leads.extend(r['warning_lead_min'] for r in paired['F0_warning_lead_times'] if r['warning_lead_min'] is not None)
                if result['status']=='physically_valid':selected.append(result['realized_metrics'])
        keys=('total_kWh','IF_SEC_kWh_per_t','plant_kWh_per_t_bars','bar_t','inventory_min_t','inventory_max_t',
              'final_inventory_t','peak_piecewise_kVA','physical_evaluation_tariff_cost_Rs')
        final_case_metrics[strategy]={key:(None if not selected else sum(r[key] for r in selected)/len(selected)) for key in keys}
        final_case_metrics[strategy+'_accepted_extrema']=dict(
            peak_kVA_max=None if not selected else max(r['peak_piecewise_kVA'] for r in selected),
            inventory_min_t=None if not selected else min(r['inventory_min_t'] for r in selected),
            inventory_max_t=None if not selected else max(r['inventory_max_t'] for r in selected))
    final_case_metrics['F0_mean_warning_lead_min']=None if not warning_leads else sum(warning_leads)/len(warning_leads)
    final_case_metrics['F0_warning_count_with_failure']=len(warning_leads)
    final_case_metrics['F2_maintenance_recommendations']=recommendations
    final_case_metrics['F2_maintenance_executed']=comparison['final']['F2']['maintenance_count']
    final_case_metrics['F2_services_in_independently_accepted_days']=accepted_services
    final_case_metrics['F2_service_commitments_in_failed_days']=comparison['final']['F2']['maintenance_count']-accepted_services
    paired_table=pd.read_parquet(ROOT/'final_paired_deltas.parquet')
    final_case_metrics['paired_mean_deltas']={key:(None if paired_table.empty else float(paired_table[key].mean()))
        for key in ('energy_delta_kWh','synthetic_tariff_delta_Rs','bar_delta_t','corrective_downtime_delta_hours','preventive_service_hours')}
    paired_physical=[]
    for seed in s['final']:
        for day in s['calendar_days']:
            record=json.loads((ROOT/'final'/f'seed_{seed}_day_{day}'/'matched_comparison.json').read_text())
            if record['paired_physical_deltas'] is not None:paired_physical.append(record['paired_physical_deltas'])
    final_case_metrics['paired_physical_delta_means']={} if not paired_physical else {
        key:sum(row[key] for row in paired_physical)/len(paired_physical) for key in paired_physical[0]}
    attribution_counts=comparison['final']['service_attribution_counts']
    resolved=sum(attribution_counts[key] for key in ('averted_within_24h','unnecessary_24h','failure_despite_service'))
    final_case_metrics['unnecessary_rate_among_resolved_services']=None if not resolved else attribution_counts['unnecessary_24h']/resolved
    final_case_metrics['attribution_resolved_services']=resolved
    final_case_metrics['executed_service_minutes']=service_minutes
    write_json(ROOT/'final_metric_context.json',final_case_metrics)
    regression=json.loads((ROOT/'e4_regression'/'seed_2001_day_14'/'e4_f0_equivalence.json').read_text())
    if not all(regression[k] for k in ('controls_identical','physical_metrics_identical','status_identical')):
        raise RuntimeError('Frozen E4 regression failed')
    testlog=Path('data/tmp/phase2f_full_tests.log')
    if not testlog.is_file():raise RuntimeError('Full test suite has not run')
    # Windows PowerShell redirection writes UTF-16; preserve the original bytes.
    raw_log=testlog.read_bytes()
    test_output=raw_log.decode('utf-16' if raw_log.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    match=re.search(r'(\d+) passed',test_output)
    if not match or any(x in test_output for x in (' failed',' error')):
        raise RuntimeError('Full test suite did not pass')
    test_count=int(match.group(1));total=len(s['calendar_days'])*sum(len(s[k]) for k in ('development','validation','final'))
    final=comparison['final'];baseline=final['F0'];maintained=final['F2']
    production_feasibility_improved=maintained['feasibility_rate']>baseline['feasibility_rate']
    # The user's exit gate requires a complete, verified comparison. Empirical
    # effectiveness is a finding, not an invented success threshold. Individual
    # failed plans remain unreleasable regardless of the archive's completion.
    release_status='COMPLETE_AUDITED_SYNTHETIC_EVALUATION'
    readiness='The deterministic interfaces and audited replay evidence are ready for Phase II-G — Supervisory Industrial Energy Copilot Agent as a supervised simulation prototype. The maintenance policy remains experimental. A supervisor must preserve the independent release gate, display infeasible continuations and synthetic assumptions, and never treat health probabilities or forecast-feasible schedules as physical guarantees. This stage does not establish autonomous shop-floor readiness.'
    f0_fault_rate=fault_summary['final']['F0']['failure_occurrence_rate']
    f2_fault_rate=fault_summary['final']['F2']['failure_occurrence_rate']
    fault_rate_text=f'F0 {f0_fault_rate:.1%}, F2 {f2_fault_rate:.1%}' if f0_fault_rate is not None and f2_fault_rate is not None else 'unavailable for one or both strategies'
    display=lambda number:'unavailable' if number is None else f'{number:.2f}'
    lead_text='unavailable' if final_case_metrics['F0_mean_warning_lead_min'] is None else f'{final_case_metrics["F0_mean_warning_lead_min"]:.1f} min'
    card=f"""# Phase II-F synthetic maintenance data card

Status: **{release_status}**. Frozen upstream stages I–E are read-only ({protected} SHA256-protected files). This dataset contains {total} attempted seed/day cases, each with F0, F1 and F2 records. Failed cases are retained.

Inputs: Phase-I V1.1 configuration and public simulation outputs; frozen Phase-II-B PredictionService; frozen Phase-II-E robust duration scenarios, constraints and matched replay. Only public closed-interval readings and completed heats enter the planner. Hidden truth and future events are evaluation-only.

Synthetic action: 15-minute MILL_01 or PMP_01 replacement; asset unavailable and wear reset to 0.02 with a seeded successor life draw. No real maintenance cost, procedure, or wear-reset evidence exists. The selected public risk policy is {policy.mill_probability:.2f}/{policy.pump_probability:.2f}, persistence {policy.persistence_observations}, four-row valid-sensor fraction {policy.minimum_valid_recent_fraction:.2f}. See `configs/maintenance_v1.yaml` and `reports/phase2f_maintenance_policy.md`.

Development seeds: {s['development']}; validation: {s['validation']}; final: {s['final']}. Working calendar days: {s['calendar_days']}. Upstream final seeds 201–210 were not used for this design. Design hash: `{json.loads((ROOT/'design_freeze.json').read_text())['design_sha256']}`.

Per case: `F0/` no-service E4-equivalent execution and risk log; `F1/` advisory-only result and published warning log; `F2/` maintenance-aware decision/replan/replay logs plus post-replay `maintenance_decision_outcomes.parquet` and `maintenance_recommendation_history.parquet`; `maintenance_attribution.parquet` for same-seed 24-hour synthetic counterfactual classification. Both post-replay ledgers are **evaluation-only**, because they join future outcomes to public decision-time inputs; they must never be loaded as runtime predictors or operator observations. The recommendation ledger distinguishes committed service from later reconfirmation, superseded windows and failed continuations. Speculative recommendations are not claimed as executed services. Full simulation folders contain latent evaluation tables and must not be used as predictive inputs. Original `prediction_history.parquet`, `health_prediction_history.parquet`, `maintenance_decisions.parquet` and replan inputs record legal publication times and do not receive post-replay fault labels. `replay_results.json` distinguishes forecast/MILP predictions from realized physical metrics and synthetic tariff results. All monetary cost is synthetic electricity tariff only; direct service cost is unknown.

The successor replay changes only intervention-dependent wear, availability and physical outcomes. Its no-action path is byte-equivalent to Phase II-E in automated tests. Original exogenous tape SHA and pre-origin heat history are checked in every valid replay. The physical checker reconstructs balances, service effects, cooling, production, inventory and piecewise peak demand independently of the MILP.

Limits: health risk is a 24-hour simulated probability, not a failure-time distribution; the planning hazard rule is an explicit assumption. Averted/unnecessary classifications apply only to the same-seed synthetic 24-hour counterfactual. `fault_process_comparison.parquet` reports evaluation-only seeded fault occurrence for all attempts, including infeasible schedules; it is not a substitute for completed physical replay. Conditional cost/energy means exclude failed runs and must be read alongside attempted-case feasibility. No real shop-floor reliability, billing or maintenance ROI claim is made.
"""
    (ROOT/'data_card.md').write_text(card,encoding='utf-8')
    (ROOT/'maintenance_config_snapshot.yaml').write_bytes(Path('configs/maintenance_v1.yaml').read_bytes())
    (ROOT/'split_manifest_snapshot.json').write_bytes(Path('configs/maintenance_split_v1.json').read_bytes())
    (ROOT/'requirements-phase2f.lock.txt').write_bytes(Path('requirements-phase2f.lock.txt').read_bytes())
    (ROOT/'validation_tests.log').write_bytes(testlog.read_bytes())
    (ROOT/'upstream_readonly_manifest.json').write_bytes(Path('configs/phase2f_readonly_manifest.json').read_bytes())
    lines=['# Phase II-F maintenance-aware robust scheduling', '',
      f'**Release status:** {release_status}. Full test suite: {test_count} passed. Protected upstream files: {protected}.',
      '', 'This status certifies completion of the audited experiment, not universal schedule feasibility or field maintenance effectiveness. Only individual `physically_valid` results with a passing independent checker are releasable.',
      '', 'The design uses the frozen PredictionService and E4 robust MILP, adding binary movable service windows for MILL_01 and PMP_01. Hard production, inventory, furnace occupancy, cooling and 7,000 kVA constraints remain in force under the inherited duration scenarios. Lexicographic objectives are robust feasibility, declared expected downtime minutes, then synthetic electricity tariff cost. A 15-minute synthetic service stops the asset and resets simulated wear; it is not a validated field procedure.',
      '', f'Development seeds {s["development"]}; validation {s["validation"]}; final {s["final"]}, each on days {s["calendar_days"]}. Seeds 201–210 remained untouched for tuning. E4/F0 persisted controls and realized metrics matched on development seed 2001/day 14.', '',
      '| Split | Strategy | Valid / attempted | Feasibility | Services | Conditional kWh | Conditional synthetic tariff Rs | Conditional summed asset-unavailability h |',
      '|---|---|---:|---:|---:|---:|---:|---:|']
    for part in ('development','validation','final'):
        for strategy in ('F0','F1','F2'):
            c=comparison[part][strategy]
            fmt=lambda x:'—' if x is None else f'{x:,.2f}'
            lines.append(f'| {part} | {strategy} | {c["physically_valid"]}/{c["attempted"]} | {c["feasibility_rate"]:.1%} | {c["maintenance_count"]} | {fmt(c["conditional_mean_total_kWh"])} | {fmt(c["conditional_mean_synthetic_cost_Rs"])} | {fmt(c["conditional_mean_total_unavailability_hours"])} |')
    lines+=['',f'Final F2–F0 absolute feasibility difference: **{final["F2"]["absolute_feasibility_change_vs_F0"]:.1%}**. Paired physically valid cases: {final["paired_physically_valid_cases"]}.',
      f'Evaluation-only final fault-tape occurrence: {fault_rate_text}. These fault rates include failed operating plans; completed physical replay rates and feasibility remain separate.',
      f'Final 24-hour attribution: {final["service_attribution_counts"]}. These are synthetic matched-counterfactual labels, not real reliability evidence.',
      f'Final F2 recommendations: {recommendations}; executed services: {final_case_metrics["F2_maintenance_executed"]}. F0 warning lead time where a prior public warning exists: {lead_text} (n={len(warning_leads)}).',
      f'Of these service records, {accepted_services} belong to independently accepted full-day replays and {final_case_metrics["F2_service_commitments_in_failed_days"]} are committed-attempt records in failed days. The latter do not establish accepted full-day production or avoided failure.',
      f'Final unnecessary-service rate among {resolved} resolved matched counterfactuals: {display(None if not resolved else 100*attribution_counts["unnecessary_24h"]/resolved)}%; {attribution_counts["undetermined_counterfactual"]} remain undetermined. Total committed service duration: {final_case_metrics["executed_service_minutes"]} minutes, including service records in failed attempts.',
      f'Paired successful-day F2–F0 mean differences: electricity {display(final["paired_mean_energy_delta_kWh"])} kWh; synthetic tariff {display(final["paired_mean_synthetic_tariff_delta_Rs"])} Rs; bars {display(final_case_metrics["paired_mean_deltas"]["bar_delta_t"])} t; corrective downtime {display(final_case_metrics["paired_mean_deltas"]["corrective_downtime_delta_hours"])} h; preventive service {display(final_case_metrics["paired_mean_deltas"]["preventive_service_hours"])} h. These pairs provide a cleaner intervention comparison than subtracting means over different sets of successful days.',
      f'Conditional final IF SEC (F0/F2): {display(final_case_metrics["F0"]["IF_SEC_kWh_per_t"])}/{display(final_case_metrics["F2"]["IF_SEC_kWh_per_t"])} kWh/t; bars: {display(final_case_metrics["F0"]["bar_t"])}/{display(final_case_metrics["F2"]["bar_t"])} t; inventory minima: {display(final_case_metrics["F0"]["inventory_min_t"])}/{display(final_case_metrics["F2"]["inventory_min_t"])} t. These are conditional on successful physical execution.',
      f'Paired mean IF SEC change: {display(final_case_metrics["paired_physical_delta_means"].get("delta_IF_SEC_kWh_per_t"))} kWh/t; inventory minimum change: {display(final_case_metrics["paired_physical_delta_means"].get("delta_inventory_min_t"))} t; final inventory change: {display(final_case_metrics["paired_physical_delta_means"].get("delta_inventory_final_t"))} t.',
      f'Accepted final F2 worst piecewise demand: {display(final_case_metrics["F2_accepted_extrema"]["peak_kVA_max"])} kVA; inventory range: {display(final_case_metrics["F2_accepted_extrema"]["inventory_min_t"])}–{display(final_case_metrics["F2_accepted_extrema"]["inventory_max_t"])} t. Every accepted replay has zero independent physical/service checker violations.',
      '', 'Energy, production, synthetic tariff cost and corrective/preventive unavailability are reported separately. Conditional means omit physically failed executions; feasibility uses every attempted case. Direct maintenance cost is unknown, so no maintenance ROI or verified real tariff saving is asserted.',
      '', 'Downtime, preventive duration and combined unavailability are summed asset-time, not wall-clock plant outage. Simultaneous MILL/PMP service contributes time for both assets; completed-production feasibility reports the resulting plant-level consequence.',
      '', 'Paired F2 differences include the service and its resulting robust rescheduling. They do not isolate a plant-efficiency intervention, and tariff shifting is not called energy saving. F0 already contains the frozen E4 energy/tariff and robustness/replanning behavior; those upstream contributions are not added again to the maintenance result.',
      '', 'F0/F1/F2 share the frozen E4 production order, generic synthetic tariff, reserve policy and `practice_loss_40` experimental practice. That synthetic practice adds the configured energy loss and is not a shop-floor recommendation or a recalibration of Phase I.',
      '', 'F1 is advisory-only and therefore shares F0 physical controls. No probability-based capacity derating or risk-only load shift was introduced: the frozen health model does not supply a defensible probability-to-capacity law. Maintenance-window decisions are limited to the explicit synthetic service mechanism.',
      '', 'Remaining limitations include the two-case policy-selection pilot, six configured service start windows, one service per asset per evaluated day, a configured zero restart delay, and no validated service-cost or failure-time model. Heat and health predictions refresh at each replan; the inherited AUX day-ahead forecast is sliced to the remaining horizon rather than refitted or refreshed. Selected days are evaluated independently from a full 30-day history; this is not a continuous multi-day maintenance campaign. The working-day pairs were selected using development data to cover wear-cycle periods, so reported failure rates describe this enriched experimental population rather than routine plant incidence.',
      '', 'Execution note: a 12-process final-evaluation launch exhausted runtime memory before six jobs could start their cases. Surviving runs were retained and missing cases retried with lower concurrency, with no parameter or design change. `infrastructure_retry_log.json` and retained startup logs distinguish these infrastructure retries from physical replay failures; no failed physical scenario was removed.',
      '', 'A representative development trace shows F2 pump service at midnight and the matched F0 pump failure at 03:37, with aligned IF power, cooling, yard inventory and public health risk:',
      '', '![Matched pump maintenance trace](figures/phase2f_matched_pump_trace.png)',
      '', 'Development seed 2001/day 28 is a separate two-asset stress example: F2 placed simultaneous 15-minute MILL/PMP services at midnight, completed 118.56 t of bars, and passed the independent checker; F0 stopped without a feasible continuation. Its avoided-failure attribution remains undetermined because the F0 adaptive replay did not complete.',
      '', 'Validation seed 2104/day 28 demonstrates a movable later-day intervention: F2 committed MILL service at 00:00 and PMP service at 16:00 after public-state replanning, completed all 13 heats, and passed the independent replay checker. F0/F1 had no feasible continuation. These validation findings did not change the frozen policy.',
      '', 'Machine-readable evidence: `replay/maintenance_v1/{development,validation,final}/seed_<id>_day_<day>/`; per-case initial/replan plans, public state/risk histories, candidate and action ledgers, complete physical replay, independent checks and retained failures. See the data card, policy report, physical audit, attribution and failure reports for limitations.',
      '', 'New files are confined to `src/energy_copilot/maintenance/`, Phase-II-F configs and lockfile, `scripts/phase2f*.py`, the two Phase-II-F test modules, Phase-II-F reports/figure/usage documentation, and `replay/maintenance_v1/`. Frozen upstream files were not edited.',
      '', readiness]
    Path('reports/phase2f_summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    attribution=[];failures=[]
    for part in ('development','validation','final'):
        a=pd.read_parquet(ROOT/f'{part}_maintenance_attribution.parquet')
        if len(a):attribution.extend(dict(split=part,**r) for r in a.to_dict('records'))
        f=pd.read_parquet(ROOT/f'{part}_failure_analysis.parquet')
        if len(f):
            enriched=[dict(split=part,**r,**observed_failure_prefix(ROOT/part/f'seed_{r["seed"]}_day_{r["day"]}',r['strategy']))
                      for r in f.to_dict('records')]
            failures.extend(enriched)
            pd.DataFrame(enriched).to_parquet(ROOT/f'{part}_failure_diagnostics.parquet',index=False)
    counts=pd.Series([r['classification'] for r in attribution]).value_counts().to_dict() if attribution else {}
    alines=['# Phase II-F maintenance attribution','',
      'Only full matched-condition synthetic replays support the limited service attribution. For each executed service, a same-seed no-service run is searched for a same-asset failure within 24 hours. A failed counterfactual remains undetermined. The intervention changes the wear lifecycle, so this does not measure real-world causal effectiveness.', '',
      f'All splits: {len(attribution)} service records; classifications {counts}.', '',
      'Per-case timing and labels are in `replay/maintenance_v1/<split>/seed_<id>_day_<day>/maintenance_attribution.parquet`. No service monetary cost was supplied; availability and synthetic tariff deltas are reported separately.']
    Path('reports/phase2f_maintenance_attribution.md').write_text('\n'.join(alines)+'\n',encoding='utf-8')
    flines=['# Phase II-F retained failure analysis','',
      f'{len(failures)} of {total*3} strategy attempts failed their continuation or independent replay checks. Every failure remains in the partition tables and feasibility denominators.', '',
      '| Split | Strategy | Seed | Day | Cause | Completed heats | Completed duration bias min | Reason |','|---|---|---:|---:|---|---:|---:|---|']
    for r in failures:
        reason=str(r.get('reason') or '').replace('|','/').replace('\n',' ')
        flines.append(f'| {r["split"]} | {r["strategy"]} | {r["seed"]} | {r["day"]} | {r.get("cause")} | {r["completed_heats"]} | {display(r["completed_duration_bias_min"])} | {reason} |')
    if not failures:flines.append('No failed attempts were observed in the declared experiment; this is not a safety guarantee.')
    flines+=['', 'Continuation failures retain completed-heat and public-state ledgers, but lack a completed independently accepted day. Their energy, tariff and full-day production are not imputed from successful runs. Service decisions in failed cases remain committed-attempt records, with undetermined failure attribution where the complete counterfactual is unavailable. A final heat deadline miss remains a scheduling/forecast failure even if preventive service removed a wear failure.']
    flines+=['', 'Duration bias uses only acknowledged completed heats and their predictions. Positive-error sums and the last public state time are retained in `*_failure_diagnostics.parquet`. They diagnose consumed schedule slack; they do not assign an unobserved future fault as the cause of an aborted day.']
    Path('reports/phase2f_failure_analysis.md').write_text('\n'.join(flines)+'\n',encoding='utf-8')
    from scripts.phase2f_validation import complete_reporting
    complete_reporting(ROOT,s,comparison,protected,test_count)
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha256(p) for p in ROOT.rglob('*') if p.is_file() and p.name!='release_manifest.json'}
    report_paths=[Path('reports')/name for name in ('phase2f_physical_audit.md','phase2f_information_boundary.md','phase2f_maintenance_policy.md',
                                                      'phase2f_summary.md','phase2f_maintenance_attribution.md','phase2f_failure_analysis.md')]
    report_paths.append(Path('reports/figures/phase2f_matched_pump_trace.png'))
    report_paths.append(Path('docs/phase2f_usage.md'))
    report_paths.append(Path('reports/phase2f_validation.json'))
    release=dict(version='maintenance_v1',label='SYNTHETIC-MAINTENANCE',status=release_status,
       final_production_feasibility_improved=production_feasibility_improved,
       final_F0_feasibility_rate=baseline['feasibility_rate'],final_F2_feasibility_rate=maintained['feasibility_rate'],
       design_sha256=json.loads((ROOT/'design_freeze.json').read_text())['design_sha256'],
       config_sha256=sha256('configs/maintenance_v1.yaml'),split_sha256=sha256('configs/maintenance_split_v1.json'),
       dependency_lock_sha256=sha256('requirements-phase2f.lock.txt'),
       protected_upstream_count=protected,tests_passed=test_count,
       release_script_sha256=sha256('scripts/phase2f_release.py'),
       validation_script_sha256=sha256('scripts/phase2f_validation.py'),
       completion_decision='PHASE II-F COMPLETE',
       figure_script_sha256=sha256('scripts/phase2f_plot.py'),
       test_sources={str(p).replace('\\','/'):sha256(p) for p in Path('tests').glob('test_phase2f_*.py')},
       full_test_log_sha256=sha256(testlog),
       hashes=hashes,reports={str(p).replace('\\','/'):sha256(p) for p in report_paths})
    write_json(ROOT/'release_manifest.json',release)
    guard();print(release_status,'files',len(hashes),'tests',test_count,flush=True)


if __name__=='__main__':main()
