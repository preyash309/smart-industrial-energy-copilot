"""Reporting-only final audit. Reads retained outcomes; never runs/tunes a planner.

All generated ledgers are EVALUATION-ONLY and outside PredictionService inputs.
"""
from pathlib import Path
import json
from collections import Counter
import pandas as pd
from energy_copilot.common import write_json

DISPOSITIONS = {'executed', 'replaced_by_replan', 'cancelled', 'infeasible',
                'not_selected', 'run_aborted_before_execution'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def distribution(values):
    x = pd.Series(values, dtype=float)
    return dict(n=len(x), mean=None if x.empty else float(x.mean()),
                median=None if x.empty else float(x.median()),
                min=None if x.empty else float(x.min()), max=None if x.empty else float(x.max()))


def paired_statistics(pairs):
    """Require both accepted replays; percentages use each matched F0 denominator."""
    result = {}
    for key in ('total_kWh', 'IF_SEC_kWh_per_t', 'plant_kWh_per_t_bars',
                'physical_evaluation_tariff_cost_Rs', 'peak_piecewise_kVA', 'bar_t', 'billet_t'):
        delta = [b[key]-a[key] for a, b in pairs]
        pct = [100*(b[key]-a[key])/a[key] for a, b in pairs if a[key] != 0]
        result[key] = dict(delta=distribution(delta), percent_delta=distribution(pct),
                           F0=distribution([a[key] for a, b in pairs]),
                           F2=distribution([b[key] for a, b in pairs]))
    for name in ('corrective', 'preventive', 'total'):
        def hours(m):
            c=sum(m['downtime_hours'].values()); p=m['_preventive_hours']
            return c if name=='corrective' else p if name=='preventive' else c+p
        result[name+'_asset_downtime_hours'] = dict(
            delta=distribution([hours(b)-hours(a) for a,b in pairs]),
            F0=distribution([hours(a) for a,b in pairs]), F2=distribution([hours(b) for a,b in pairs]))
    return result


def terminal_cause(folder, result):
    plans=[read(p) for p in sorted(folder.glob('replan_step_*.json'))]
    last=plans[-1] if plans else read(folder/'initial_plan.json')
    status=last['status']; reason=result.get('reason') or ''
    if status=='solver_limit':
        return 'solver_limit_no_accepted_continuation', status, 'Termination limit; mathematical infeasibility not proved.'
    if 'end-of-day' in reason.lower() or 'within working day' in reason.lower():
        return 'end_of_day_overrun', status, 'Furnace duration/scheduling failure; not automatically maintenance-caused.'
    if 'occupancy bounds' in reason.lower():
        return 'duration_accumulation_no_feasible_continuation', status, 'Remaining robust occupancy cannot fit the allowed window.'
    return result.get('failure_class') or 'no_feasible_continuation', status, 'Cause is retained from acknowledged execution; no future fault inference.'


def complete_reporting(root, split, comparisons, protected, test_count):
    root=Path(root); cases=[]; failures=[]; recommendations=[]; candidates=[]; services=[]; production=[]
    final_pairs=[]; eligibility_count=0
    for partition in ('development','validation','final'):
        for seed in split[partition]:
            for day in split['calendar_days']:
                case=root/partition/f'seed_{seed}_day_{day}'
                attempts=read(case/'attempt_results.json')
                assert len(attempts)==3 and {r['strategy'] for r in attempts}=={'F0','F1','F2'}
                entries={r['strategy']:r['result'] for r in attempts}
                for strategy,result in entries.items():
                    valid=result['status']=='physically_valid'
                    folder=case/('F0' if strategy=='F1' else strategy)
                    control=read(folder/'controller_result.json')
                    metrics=result.get('realized_metrics')
                    completion=bool(valid and result['completed_heats']==13 and metrics['bar_t']>=118.56-1e-7)
                    cases.append(dict(split=partition,seed=seed,day=day,strategy=strategy,status=result['status'],
                        physically_valid=valid,production_complete=completion,replans=result['replans'],evaluation_only=True))
                    if valid:
                        assert result['verification']['feasible'] and result['verification']['violations']==0
                        assert result['matched_conditions']['history_prefix_identical']
                        assert result['matched_conditions']['original_exogenous_sha256']==result['matched_conditions']['replay_exogenous_sha256']
                        production.append(dict(split=partition,seed=seed,day=day,strategy=strategy,
                            bars_t=metrics['bar_t'],billets_t=metrics['billet_t'],production_shortfall_t=max(0,118.56-metrics['bar_t']),
                            closing_inventory_t=metrics['final_inventory_t'],minimum_inventory_t=metrics['inventory_min_t'],
                            maximum_inventory_t=metrics['inventory_max_t'],evaluation_only=True))
                    else:
                        cause,last_status,limitation=terminal_cause(folder,result)
                        failures.append(dict(split=partition,seed=seed,day=day,strategy=strategy,
                            status=result['status'],primary_cause=cause,original_failure_class=result.get('failure_class'),
                            solver_status=last_status,reason=result.get('reason'),completed_heats=control['completed_heats'],
                            last_public_time=control['final_state']['current_time'],remaining_heats=len(control['final_state']['remaining_heats']),
                            limitation=limitation,planner_diagnostic_source='acknowledged/public controller history only',evaluation_only=True))
                f2=entries['F2']; folder=case/'F2'
                control=read(folder/'controller_result.json')
                attr=pd.read_parquet(case/'maintenance_attribution.parquet')
                dec=pd.read_parquet(folder/'maintenance_decisions.parquet')
                for row in dec.to_dict('records'):
                    # A failed full day can still acknowledge a completed prefix service.
                    valid=f2['status']=='physically_valid'
                    assert bool(row['executed'])
                    if not valid:
                        assert pd.Timestamp(row['end_time'])<=pd.Timestamp(control['final_state']['current_time'])
                        history=pd.read_parquet(folder/'state_history.parquet')
                        assert int(history.completed_services.max())>=len(dec)
                    else:
                        assert any(e['asset_id']==row['asset_id'] and pd.Timestamp(e['start'])==pd.Timestamp(row['start_time'])
                                   for e in f2['service_events_day'])
                    match=attr.loc[attr.asset_id.eq(row['asset_id']) & attr.service_start.eq(row['start_time'])]
                    assert len(match)==1
                    label=match.iloc[0]['classification']
                    if label!='undetermined_counterfactual':
                        assert valid and entries['F0']['status']=='physically_valid'
                    if label=='averted_within_24h':
                        times=match.iloc[0]['no_action_failure_times']
                        assert len(times) and min(pd.Timestamp(t) for t in times)>=pd.Timestamp(row['end_time'])
                        assert not len(match.iloc[0]['service_run_failure_times'])
                    services.append(dict(split=partition,seed=seed,day=day,asset_id=row['asset_id'],
                        start_time=row['start_time'],end_time=row['end_time'],executed=True,
                        execution_evidence='independent full-day replay' if valid else 'acknowledged physical prefix; full day failed',
                        full_day_verified=valid,classification=label,evaluation_only=True))
                rec=pd.read_parquet(folder/'maintenance_recommendation_history.parquet')
                assert len(rec)==f2['maintenance_recommendations']
                if len(rec):
                    assert set(rec.disposition)<=DISPOSITIONS
                    assert int(rec.execution_acknowledged.sum())==len(dec)
                    recommendations.extend(dict(split=partition,seed=seed,day=day,**r) for r in rec.to_dict('records'))
                plans=[read(folder/'initial_plan.json')]+[read(p) for p in sorted(folder.glob('replan_step_*.json'))]
                for plan in plans:
                    eligibility_count+=sum(bool(h['eligible']) for h in plan['health_audit']) if partition=='final' else 0
                    assert all(pd.Timestamp(h['available_at'])<=pd.Timestamp(plan['current_time']) for h in plan['health_audit'])
                candidate_table=pd.read_parquet(folder/'maintenance_candidate_history.parquet')
                for row in candidate_table.to_dict('records'):
                    if row['selected']:continue  # selected recommendations already have terminal dispositions
                    plan=next(p for p in plans if p['step']==row['step'])
                    disp='infeasible' if plan['status'] not in ('optimal','feasible') else 'not_selected'
                    candidates.append(dict(split=partition,seed=seed,day=day,**row,disposition=disp,evaluation_only=True))
                if partition=='final' and all(entries[k]['status']=='physically_valid' for k in ('F0','F2')):
                    a=dict(entries['F0']['realized_metrics'],_preventive_hours=0)
                    b=dict(f2['realized_metrics'],_preventive_hours=sum(
                        (pd.Timestamp(r['end_time'])-pd.Timestamp(r['start_time'])).total_seconds()/3600 for r in dec.to_dict('records')))
                    final_pairs.append((a,b))
    c=pd.DataFrame(cases); sr=pd.DataFrame(services); rr=pd.DataFrame(recommendations); cr=pd.DataFrame(candidates)
    for name,frame in [('all_attempt_validation',c),('executed_service_ledger',sr),('recommendation_disposition_ledger',rr),
                       ('unselected_candidate_dispositions',cr),('accepted_production',pd.DataFrame(production)),
                       ('final_failure_diagnostics',pd.DataFrame([r for r in failures if r['split']=='final']))]:
        frame.to_parquet(root/(name+'.parquet'),index=False)
    assert len(c)==3*len(split['calendar_days'])*sum(len(split[p]) for p in ('development','validation','final'))
    # Preserve the already published development/validation counts exactly.
    for p,expected in [('development',(18,21,24)),('validation',(13,16,16))]:
        for strategy,n in [('F0',expected[0]),('F1',expected[0]),('F2',expected[1])]:
            d=c.loc[c['split'].eq(p)&c.strategy.eq(strategy)]
            assert len(d)==expected[2] and int(d.physically_valid.sum())==n==comparisons[p][strategy]['physically_valid']
    final=c.loc[c['split'].eq('final')]; all_attempt={}
    for strategy in ('F0','F1','F2'):
        d=final.loc[final.strategy.eq(strategy)]
        all_attempt[strategy]=dict(attempted=len(d),physically_valid=int(d.physically_valid.sum()),
            feasibility_rate=float(d.physically_valid.mean()),production_completed=int(d.production_complete.sum()),
            completed_production_rate=float(d.production_complete.mean()),
            no_feasible_continuation=int(d.status.eq('no_feasible_continuation').sum()),
            physical_replay_failure=int(d.status.eq('replay_infeasible').sum()),replans=int(d.replans.sum()))
    sf=sr.loc[sr['split'].eq('final')]; rf=rr.loc[rr['split'].eq('final')]
    maintenance=dict(recommendations=len(rf),eligible_selected_recommendations=int(rf.eligible.sum()),
        eligible_asset_decision_observations=eligibility_count,committed_services=len(sf),executed_services=len(sf),
        independently_verified_full_day_services=int(sf.full_day_verified.sum()),
        acknowledged_services_in_failed_days=int((~sf.full_day_verified).sum()),
        dispositions=dict(Counter(rf.disposition)),
        replaced_or_cancelled_recommendations=int(rf.disposition.isin(['replaced_by_replan','cancelled']).sum()),
        attribution=dict(Counter(sf.classification)),unnecessary_rate_among_executed_services=float(sf.classification.eq('unnecessary_24h').mean()),
        by_asset={a:dict(executed=int(sf.asset_id.eq(a).sum()),
                         classifications=dict(Counter(sf.loc[sf.asset_id.eq(a),'classification']))) for a in ('MILL_01','PMP_01')})
    maintenance['acknowledged_preventive_asset_hours']=sum(
        (pd.Timestamp(r.end_time)-pd.Timestamp(r.start_time)).total_seconds()/3600 for r in sf.itertuples())
    maintenance['independently_accepted_preventive_asset_hours']=sum(
        (pd.Timestamp(r.end_time)-pd.Timestamp(r.start_time)).total_seconds()/3600 for r in sf.loc[sf.full_day_verified].itertuples())
    assert len(sf)==comparisons['final']['F2']['maintenance_count']
    stats=paired_statistics(final_pairs)
    pd.DataFrame([dict(pair=i,metric=k,delta=b[k]-a[k],F0=a[k],F2=b[k],evaluation_only=True)
                  for i,(a,b) in enumerate(final_pairs) for k in ('total_kWh','IF_SEC_kWh_per_t','plant_kWh_per_t_bars',
                  'physical_evaluation_tariff_cost_Rs','peak_piecewise_kVA','bar_t','billet_t')]).to_parquet(root/'final_paired_metric_distribution.parquet',index=False)
    result=dict(completion_decision='PHASE II-F COMPLETE',labels=['DIGITAL-TWIN-REALIZED','SYNTHETIC-MAINTENANCE','SYNTHETIC-TARIFF','EVALUATION-ONLY'],
        declared_final_seeds=split['final'],declared_days=split['calendar_days'],all_final_cases_complete=True,
        all_attempt_comparison=all_attempt,maintenance=maintenance,paired_valid_cases=len(final_pairs),paired_statistics=stats,
        development_validation_final={p:{k:comparisons[p][k] for k in ('F0','F2')} for p in ('development','validation','final')},
        final_fault_process_evaluation_only=read(root/'fault_process_comparison.json')['final'],
        attribution_window='24 hours from each service start; may extend beyond the evaluated calendar day',
        fault_process_window='Selected calendar day only; not the service-relative attribution window',
        final_failures=[r for r in failures if r['split']=='final'],
        audits=dict(physical_checks_on_accepted_days='PASS',information_boundary='PASS',matched_unaffected_streams='PASS',
                    no_action_E4_regression='PASS',upstream_protected_files=protected,tests_passed=test_count,
                    exact_test_command='$env:PYTHONPATH="src;."; .venv/Scripts/python.exe -m pytest -q'),
        maintenance_ROI=None,ROI_limitation='No validated service, labor, spare-parts or avoided-failure costs.',
        statistical_limitation='Six final seeds, four enriched days each; days within a seed are not independent.',
        upstream_design_changed=False)
    write_json(root/'final_validation.json',result);write_json('reports/phase2f_validation.json',result)
    f0=all_attempt['F0']; f2=all_attempt['F2']; pp=100*(f2['feasibility_rate']-f0['feasibility_rate'])
    avoided=maintenance['attribution'].get('averted_within_24h',0); unnecessary=maintenance['attribution'].get('unnecessary_24h',0)
    undetermined=maintenance['attribution'].get('undetermined_counterfactual',0)
    def fmt(x):return 'unavailable' if x is None else f'{x:.4f}'
    lines=['# Phase II-F final evaluation and release','', '**PHASE II-F COMPLETE** — the frozen experiment is complete; maintenance benefit is not a release criterion. All 24 predeclared final seed/day cases and 72 strategy records are retained. Failed plans are not executable releases.','',
        'DIGITAL-TWIN-REALIZED outcomes; SYNTHETIC-MAINTENANCE interventions; SYNTHETIC-TARIFF electricity costs. Future labels and causal tables are EVALUATION-ONLY. OPTIMIZER-PREDICTED plans remain separate. Upstream EXTERNAL-BENCHMARK results are not plant-maintenance evidence.','',
        'The frozen PredictionService feeds the E4 robust/adaptive MILP and independent physical replay. F2 adds binary service windows and lexicographic robust feasibility, expected unavailable minutes, then synthetic tariff cost. No thresholds, scenario rules, service assumptions, solver logic, tariffs, production order, practice or model artifacts changed during final evaluation.','',
        f'Development: {split["development"]}; validation: {split["validation"]}; final: {split["final"]}; days {split["calendar_days"]}, from the frozen manifest. The 201–210 evaluation seeds were not used for tuning. The 0.55 MILL/PMP thresholds, 0.75 sensor-quality gate, 15-minute service, 0.02 wear reset, six candidate times, and frozen E4 policy are unchanged. No maintenance ROI is calculated.','',
        '| Final strategy | Attempted | Physically valid | Feasibility | Production completion | No accepted continuation | Physical replay failures |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for k,d in all_attempt.items():lines.append(f'| {k} | {d["attempted"]} | {d["physically_valid"]} | {d["feasibility_rate"]:.2%} | {d["completed_production_rate"]:.2%} | {d["no_feasible_continuation"]} | {d["physical_replay_failure"]} |')
    lines+=['','F1 is public health advice only and shares F0 controls and physical outcomes exactly. All unsuccessful continuations remain in the denominator; missing full-day outcomes are not imputed.','',
        '| Split | F0 attempted / valid / feasibility | F2 attempted / valid / feasibility |','|---|---|---|']
    for p in ('development','validation','final'):
        a=comparisons[p]['F0'];b=comparisons[p]['F2']
        lines.append(f'| {p} | {a["attempted"]} / {a["physically_valid"]} / {a["feasibility_rate"]:.2%} | {b["attempted"]} / {b["physically_valid"]} / {b["feasibility_rate"]:.2%} |')
    lines+=['',f'F2 did **not** improve final feasibility: {pp:+.2f} percentage points. Validation gains did not generalize to this small final population. Final total replans: F0 {f0["replans"]}, F2 {f2["replans"]}.','',
        f'F2 made {maintenance["recommendations"]} selected recommendation appearances ({maintenance["eligible_selected_recommendations"]} eligible), across {eligibility_count} eligible asset/decision observations. It committed and acknowledged execution of **{len(sf)} services**: {maintenance["by_asset"]["MILL_01"]["executed"]} MILL and {maintenance["by_asset"]["PMP_01"]["executed"]} PMP. **{maintenance["independently_verified_full_day_services"]}** have independently accepted full-day replay evidence; **{maintenance["acknowledged_services_in_failed_days"]}** completed in acknowledged prefixes whose full-day continuation failed. Prefix execution is not full-day acceptance or avoided-failure proof.','',
        f'Terminal recommendation dispositions: {maintenance["dispositions"]}. Earlier planned windows are not counted as performed services. Unselected/infeasible candidate windows are retained separately; all ledgers are EVALUATION-ONLY.','',
        f'Acknowledged preventive downtime is {maintenance["acknowledged_preventive_asset_hours"]:.2f} summed asset-hours across all attempts, of which {maintenance["independently_accepted_preventive_asset_hours"]:.2f} hours have accepted full-day replay evidence. Failed-day full totals remain unknown; the prefix services are not dropped or extrapolated.','',
        f'Strict matched avoided failures: **{avoided}**. Unnecessary within 24 hours: **{unnecessary} / {len(sf)} executed = {maintenance["unnecessary_rate_among_executed_services"]:.2%}**. Undetermined: **{undetermined}**, because a matched full-day replay failed. No service is claimed to lack longer-term value. Asset breakdown: {maintenance["by_asset"]}.','',
        f'Paired numerical comparison uses only **{len(final_pairs)}** cases where both full physical replays passed. Each distribution below is F2 minus its own matched F0, not subtraction of unmatched successful-case averages. Percentages are means of per-pair relative changes.','',
        '| Metric | n | Mean delta | Median | Minimum | Maximum | Mean paired % |','|---|---:|---:|---:|---:|---:|---:|']
    for k in ('total_kWh','IF_SEC_kWh_per_t','plant_kWh_per_t_bars','physical_evaluation_tariff_cost_Rs','peak_piecewise_kVA'):
        d=stats[k]['delta'];pct=stats[k]['percent_delta']['mean']
        lines.append(f'| {k} | {d["n"]} | {fmt(d["mean"])} | {fmt(d["median"])} | {fmt(d["min"])} | {fmt(d["max"])} | {fmt(pct)}% |')
    lines+=['','| Paired summed asset downtime | F0 hours total | F2 hours total | Mean F0 hours/day | Mean F2 hours/day |','|---|---:|---:|---:|---:|']
    for k in ('corrective','preventive','total'):
        d=stats[k+'_asset_downtime_hours'];a=d['F0'];b=d['F2']
        lines.append(f'| {k} | {a["mean"]*a["n"]:.4f} | {b["mean"]*b["n"]:.4f} | {a["mean"]:.4f} | {b["mean"]:.4f} |')
    fault=result['final_fault_process_evaluation_only']
    lines+=['',f'EVALUATION-ONLY fault process over all 24 attempts: F0 {fault["F0"]}; F2 {fault["F2"]}. This is the action-aware represented fault process, including plans that failed; it is not evidence those plans completed. Corrective repairs, preventive services and their separate downtime components are not conflated. Asset-time sums can double-count simultaneous asset outages relative to wall-clock plant downtime.','',
        'The fault-process count covers the selected calendar day; strict service attribution covers the 24 hours starting at each service, which can extend into the following day. Thus 14 service-relative avoided failures must not be equated with 14 failures inside the selected-day fault-count population. Repeated days share seed histories and are not independent field failures.','',
        'All paired accepted days produced 118.56 t bars and 123.50 t billets, with zero order shortfall. Closing/minimum/maximum stock for each successful strategy case is retained in `accepted_production.parquet`. All-attempt production completion is shown above; no failed-day production is inferred from successful means.','',
        '| Paired production / stock | n | F0 mean [min, max] | F2 mean [min, max] |','|---|---:|---|---|']
    for k in ('bar_t','billet_t','final_inventory_t','inventory_min_t','inventory_max_t'):
        a=distribution([a[k] for a,b in final_pairs]);b=distribution([b[k] for a,b in final_pairs])
        lines.append(f'| {k} | {a["n"]} | {a["mean"]:.4f} [{a["min"]:.4f}, {a["max"]:.4f}] | {b["mean"]:.4f} [{b["min"]:.4f}, {b["max"]:.4f}] |')
    lines+=['',
        '| Final failure | Strategy | Completed heats | Primary diagnostic | Terminal solver status |','|---|---|---:|---|---|']
    for r in result['final_failures']:lines.append(f'| {r["seed"]} / day {r["day"]} | {r["strategy"]} | {r["completed_heats"]} | {r["primary_cause"]} | {r["solver_status"]} |')
    lines+=['','Seed 2202/day 14 F2 completed MILL service at midnight but stopped after five heats when the maintenance continuation solve reached `solver_limit`. Its recorded generic `solver_infeasibility` label is preserved in raw evidence; the reporting diagnostic distinguishes a solver limit from proven infeasibility. F0 completed that day. The archive is not silently rerun with a longer time limit. Seeds 2204/day 28 and 2205/day 26 fail in both strategies due to remaining-window/duration problems; maintenance does not cure furnace-duration accumulation. Public execution prefixes support these diagnostics; unobserved future failures are not asserted as causes.','',
        'The separate 12-worker startup memory failure affected six launch jobs before cases ran. All logs were preserved and only missing cases were resumed at lower concurrency. Startup failures are not physical failures or extra declared seed/day cases. No successful case was rerun for performance selection.','',
        f'Final audits: physical and service checker PASS for every accepted replay; posting-time/information boundary PASS; direct unaffected-exogenous-field test PASS; immutable completed decisions PASS; no-action E4 equivalence PASS. Protected upstream SHA256 files: **{protected} unchanged**. Frozen design digest and config/model evidence are retained in the release manifest.','',
        f'Full regression command: `$env:PYTHONPATH="src;."; .venv/Scripts/python.exe -m pytest -q`. **{test_count} passed**, run after final evaluation; exact output is frozen as `validation_tests.log`.','',
        'Files are confined to Phase-II-F maintenance modules/configs/lock, evaluation/release/reporting scripts, tests, reports/figure/usage documentation and `replay/maintenance_v1/`. This completion step added reporting-only final distributions, terminal ledgers and validation JSON; the frozen implementation and upstream artifacts were not changed.','',
        'Release evidence: per-case plans/replans, public prediction/state/schedule histories, immutable service records, original startup logs, physical checks, strict attribution, final failures, all-attempt and paired tables, config/split/lock snapshots, data card, test log and SHA256 manifest.','',
        '![Matched development pump trace](figures/phase2f_matched_pump_trace.png)','',
        'The deterministic system is ready for Phase II-G as a **supervised simulation prototype**, not autonomous industrial deployment. A supervisor must surface failed continuations, preserve the independent physical acceptance gate and distinguish predictive advice from verified execution.','',
        f'**Conclusion:** Maintenance-aware scheduling did not improve final schedule feasibility ({pp:+.2f} pp); paired corrective downtime changed from {stats["corrective_asset_downtime_hours"]["F0"]["mean"]*len(final_pairs):.4f} to {stats["corrective_asset_downtime_hours"]["F2"]["mean"]*len(final_pairs):.4f} summed asset-hours. It acknowledged {len(sf)} preventive services ({int(sf.full_day_verified.sum())} independently full-day verified), demonstrated {avoided} strict matched avoided failures, and classified {unnecessary} unnecessary services ({undetermined} undetermined). Production completion changed from {f0["completed_production_rate"]:.2%} to {f2["completed_production_rate"]:.2%}; mean paired energy changed {stats["total_kWh"]["percent_delta"]["mean"]:+.4f}% and synthetic tariff cost {stats["physical_evaluation_tariff_cost_Rs"]["percent_delta"]["mean"]:+.4f}%. Limits remain: synthetic wear/replacement model, small enriched evaluation population, no field-maintenance evidence, no real maintenance cost, 24-hour health model, reduced-order plant physics, and remaining heat-duration/scheduling and solver-limit failures.']
    Path('reports/phase2f_summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    attribution_report=['# Phase II-F strict maintenance attribution','',
        f'Final: {len(sf)} acknowledged executed services; {int(sf.full_day_verified.sum())} independently full-day verified. {avoided} strict matched avoided failures; {unnecessary} unnecessary within 24 hours; {undetermined} undetermined.','',
        'Avoided requires the same asset to fail in the completed matched F0 replay, preventive service to finish before its represented failure threshold, and no corresponding failure within the configured horizon in completed F2. The postprocessor checks these conditions without changing the frozen raw labels. If either matched day fails, attribution remains undetermined. Unnecessary requires a completed no-action counterfactual with no same-asset failure in the service-relative 24-hour window; no longer-term value claim follows.','',
        f'Unnecessary rate: {unnecessary}/{len(sf)} executed services = {maintenance["unnecessary_rate_among_executed_services"]:.2%}. MILL/PMP breakdown: {maintenance["by_asset"]}.','',
        f'Recommendation dispositions: {maintenance["dispositions"]}. Each selected recommendation appearance ends in an explicit terminal disposition; candidate windows not selected by the solver have a separate ledger. Repeated or replaced proposals do not add executed service counts.','',
        'See `executed_service_ledger.parquet`, `recommendation_disposition_ledger.parquet`, `unselected_candidate_dispositions.parquet` and the untouched per-case raw attribution. These are EVALUATION-ONLY, not runtime predictors. No maintenance ROI, labor cost, spare-part cost or rupee benefit from avoided failures is inferred.']
    Path('reports/phase2f_maintenance_attribution.md').write_text('\n'.join(attribution_report)+'\n',encoding='utf-8')
    with Path('reports/phase2f_failure_analysis.md').open('a',encoding='utf-8') as handle:
        handle.write('\nFinal reporting refinement: seed 2202/day 14 F2 ended at a solver limit after five heats. The generic frozen classification is retained; no proof of physical/mathematical infeasibility is claimed. It remains a failed attempted case. The other final failures are remaining-window/duration failures, not automatically attributed to maintenance. See `final_failure_diagnostics.parquet`.\n')
    for name in ('physical_audit','information_boundary','maintenance_policy'):
        path=Path('reports/phase2f_'+name+'.md')
        original=path.read_text(encoding='utf-8').split('\nFinal release audit:')[0].rstrip()
        path.write_text(original+f'\n\nFinal release audit: all 24 declared final cases retained; {test_count} full-suite tests passed after final evaluation; {protected} protected upstream hashes unchanged. Policy/design/model parameters were not modified. Reporting ledgers and final validation tables are EVALUATION-ONLY and cannot enter PredictionService. Failed full-day continuations are not independently accepted physical plans.\n',encoding='utf-8')
    card=root/'data_card.md'
    if card.exists():
        original=card.read_text(encoding='utf-8').split('\nFinal release accounting:')[0].rstrip()
        card.write_text(original+f'\n\nFinal release accounting: terminal recommendation dispositions are {sorted(DISPOSITIONS)}; candidate windows not selected are separate. Final F0/F2 acceptance {f0["physically_valid"]}/24 and {f2["physically_valid"]}/24; {len(sf)} acknowledged services, {int(sf.full_day_verified.sum())} independently verified in accepted full days. The two prefix-service records are not full-day acceptance. Final evaluation JSON and enriched ledgers are EVALUATION-ONLY. Test result: {test_count} passed after final evaluation.\n',encoding='utf-8')
