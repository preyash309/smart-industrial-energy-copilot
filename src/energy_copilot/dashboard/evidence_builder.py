"""Offline/worker projection of PUBLIC evidence. No events or latent-table reads."""
from pathlib import Path
import json
import pandas as pd
from energy_copilot.common import load_config,values,write_json
from energy_copilot.analytics.build import PublicInputs,HEAT_INPUTS,PRODUCTION_INPUTS,clean_readings,production_register,slot_table,heat_table
from energy_copilot.analytics.diagnostics import diagnostic_candidates
from .contracts import ROOT,file_hash,read_json,validate_bundle
from .scenarios import scenario

def records(frame):return json.loads(frame.to_json(orient='records',date_format='iso',date_unit='ns'))

def rejected_excerpt(packet,rows):
    """Read-only UI excerpt, not a new VERIFIED supervisor decision."""
    from energy_copilot.supervisor.contracts import digest
    first=packet['alternatives_considered'][0]
    rejected=next(r['payload']['response'] for r in rows if r['kind']=='tool_result' and r['payload']['tool']=='replay_candidate_plan'
        and r['payload']['response']['schedule_id']==first['schedule_id'])
    view=dict(packet);view.update(decision_id='rejected_excerpt_'+digest(first)[:20],disposition='PROPOSED',outcome='NO_VERIFIED_RECOMMENDATION',
        optimizer_plan=first,replay_outcome=rejected,independent_check=None,comparison=None,alternatives_considered=[first],
        recommendation='Recommendation withheld: this forecast-feasible candidate failed digital-twin replay.',
        grounded_values=[],card_sentences=[],required_human_action='Review rejection; no executable plan.')
    return view

def build_bundle(key,episode,worker,seed,day,excerpt=False):
    s=scenario(key);episode=Path(episode);worker=Path(worker)
    packet=read_json(episode/'decision_packet.json')
    audit=[json.loads(x) for x in (episode/'audit.jsonl').read_text().splitlines()]
    canonical=packet['decision_id']
    if excerpt:packet=rejected_excerpt(packet,audit)
    identity=packet['optimizer_plan']['schedule_id'];origin=pd.Timestamp(packet['timestamp']);end=origin+pd.Timedelta(days=1)
    rawplan=read_json(worker/(identity+'.json'));plan=rawplan['plan']
    projections=[];eligibility=[]
    for row in audit:
        if row['kind']=='tool_result' and row['payload']['tool']=='get_maintenance_candidates':eligibility=row['payload']['response']['eligible_assets']
    public_dir=worker/identity/'physical_evaluation_only'
    if not (public_dir/'readings.parquet').exists():
        # An excerpt may use only pre-origin history from its SAME run's final replay.
        candidates=list(worker.glob('*/physical_evaluation_only/readings.parquet'))
        public_dir=candidates[0].parent if candidates else None
    history=[];heatrows=[];observed=[];assets=[];alerts=[];public_summary=None;prior_schedule=[]
    if public_dir is not None:
        cfg=values(load_config(ROOT/'data/processed/sim_v1.1/config_snapshot.yaml'))
        settings=dict(clock_minutes=cfg['clock_minutes'],timezone=cfg['timezone'],start=cfg['start'],calendar=cfg['calendar'],initial_yard=cfg['material']['initial_yard'])
        r=pd.read_parquet(public_dir/'readings.parquet');h=pd.read_parquet(public_dir/'heats.parquet')[list(HEAT_INPUTS)];p=pd.read_parquet(public_dir/'production.parquet')[list(PRODUCTION_INPUTS)]
        inputs=PublicInputs(r,h,p,settings);a=values(load_config(ROOT/'configs/analytics_v1.yaml'))
        cleaned=clean_readings(inputs,a['parameters']);production=production_register(inputs,a['parameters'])
        slots,_=slot_table(cleaned,production,inputs,a);heats,_=heat_table(inputs,slots,a)
        di=diagnostic_candidates(heats,slots,a['parameters'])[0]
        # Historical observations and retrospective verification outcomes stay separate.
        history=records(cleaned.loc[(cleaned.available_at<=origin)&(cleaned.timestamp>=origin-pd.Timedelta(days=1)),
            ['timestamp','available_at','asset_id','kW','kWh','kVA','pf','vibration_mm_s','temp_C','state','energy_best_kWh']])
        past=heats.loc[heats.available_at<=origin];prior=past.loc[past.start_time.dt.date==past.start_time.max().date()] if len(past) else past
        prior_schedule=records(prior[['heat_id','start_time','end_time']])
        if packet['replay_outcome']['physically_valid']:
            hd=heats.loc[(heats.start_time>=origin)&(heats.start_time<end)]
            heatrows=records(hd[['heat_id','start_time','end_time','kWh','SEC_kWh_per_t','expected_kWh','expected_SEC','residual_SEC','duration_min','tap_temp_C','baseline_available_at']])
            rd=cleaned.loc[(cleaned.timestamp>=origin)&(cleaned.timestamp<end)]
            observed=records(rd[['timestamp','available_at','asset_id','kW','kVA','energy_best_kWh','state','tariff_band']])
            asset=rd.groupby('asset_id').agg(kWh=('energy_best_kWh',lambda x:x.sum(min_count=1)),valid_samples=('energy_best_kWh','count')).reset_index()
            assets=records(asset)
            prod=production.loc[(production.interval_start>=origin)&(production.interval_start<end)]
            public_summary=dict(bars_t=float(prod.bar_t.sum()),billets_t=float(prod.billet_t.sum()),IF_SEC=float(hd.kWh.sum()/hd.liquid_t.sum()),
                heat_count=len(hd),label='COMPLETED-HEAT/SHIFT REGISTERS · REPLAY DAY',source=str(public_dir.relative_to(ROOT)))
            alerts=records(di.loc[(di.available_at>origin)&(di.available_at<=end)].tail(10))
        else:
            alerts=records(di.loc[(di.available_at<=origin)&(di.available_at>origin-pd.Timedelta(days=1))].tail(10))
    metadata=dict(scenario=key,title=s['title'],story=s['story'],seed=seed,day=day,origin=origin.isoformat(),
        snapshot_id=packet['snapshot']['snapshot_id'],canonical_source_decision_id=canonical,
        scope='REJECTED CANDIDATE EXCERPT · subsequent recovery shown separately' if excerpt else 'PRECOMPUTED VERIFIED DEMO' if packet['outcome']=='VERIFIED_RECOMMENDATION' else 'PRECOMPUTED REJECTED DEMO',
        source_episode=episode.relative_to(ROOT).as_posix(),source_worker=worker.relative_to(ROOT).as_posix(),
        source_hashes={str(episode.relative_to(ROOT)/'decision_packet.json'):file_hash(episode/'decision_packet.json'),
            str(worker.relative_to(ROOT)/(identity+'.json')):file_hash(worker/(identity+'.json'))},
        predictive_as_of=origin.isoformat(),replay_evaluation_day=origin.date().isoformat(),
        missing_public_trace=public_dir is None,maintenance_eligible_assets=eligibility)
    schedule=dict(schedule_id=identity,heats=plan['schedule'],load=plan['load_trajectory'],
        inventory=plan['inventory_trajectory'],metrics=plan['predicted_metrics'],prior_observed_heats=prior_schedule,
        reference_note='Reference timeline is the latest completed observed day in this same run; not the matched-cost counterfactual.',
        maintenance_actions=packet['optimizer_plan']['maintenance_actions'],
        initial_rejected=packet['alternatives_considered'][0]['schedule_id'] if len(packet['alternatives_considered'])>1 else None)
    bundle=dict(metadata=metadata,packet=packet,schedule=schedule,observed_history=history,replay_observations=observed,
        heat_analytics=heatrows,asset_energy=assets,diagnostics=alerts,public_summary=public_summary)
    return validate_bundle(bundle)

def build_demo():
    base=ROOT/'dashboard/evidence_v1'
    if (base/'manifest.json').exists():raise ValueError('Demo evidence already exists; use a successor version')
    for key in ('normal','maintenance','rejection','recovery'):
        s=scenario(key);root=ROOT/'supervision/supervisor_v1/integration'/s['attempt']
        bundle=build_bundle(key,root/'episode',root/'execution_gateway_evaluation_only',s['seed'],s['day'],key=='rejection')
        write_json(base/key/'bundle.json',bundle)
    metrics=deck_metrics();write_json(ROOT/'dashboard_deck_metrics.json',metrics)
    write_json(base/'impact.json',metrics)
    paths=list(base.glob('*/bundle.json'))+[base/'impact.json']
    write_json(base/'manifest.json',dict(version='dashboard_demo_v1',files={p.relative_to(base).as_posix():file_hash(p) for p in paths}))

def deck_metrics():
    dpath='replay/optimizer_v1/primary/paired_comparison.json';d=read_json(ROOT/dpath)['comparisons']['conservative_synthetic']
    epath='replay/robustness_v1/final_regression_comparison.json';e=read_json(ROOT/epath)
    fpath='reports/phase2f_validation.json';f=read_json(ROOT/fpath)
    rows=[]
    def add(metric,value,unit,label,artifact,field,scenario,caveat):
        rows.append(dict(metric=metric,value=value,unit=unit,evidence_label=label,source_artifact=artifact,source_field=field,
            source_sha256=file_hash(ROOT/artifact),scenario=scenario,caveat=caveat))
    add('Matched electricity reduction',d['kWh_reduction_pct'],'%','DIGITAL-TWIN-REALIZED · SYNTHETIC-PRACTICE',dpath,'comparisons.conservative_synthetic.kWh_reduction_pct','Phase II-D seed 42 / S0 vs conservative_synthetic','Single matched reduced-order simulation; not field savings.')
    add('Matched synthetic tariff reduction',d['physical_evaluation_cost_reduction_pct'],'%','DIGITAL-TWIN-REALIZED · SYNTHETIC-TARIFF · SYNTHETIC-PRACTICE',dpath,'comparisons.conservative_synthetic.physical_evaluation_cost_reduction_pct','Phase II-D seed 42 / S0 vs conservative_synthetic','Synthetic 4/8/12 Rs/kWh; neither actual billing nor energy reduction alone.')
    for strategy in ('E0','E4'):
        add(strategy+' final feasible cases',e[strategy]['feasible'],'days / 10','HELD-OUT DIGITAL-TWIN EVALUATION',epath,strategy+'.feasible','Phase II-E final 201–210','Combined policy/grid/reserve/scenario/adaptive comparison; not an isolated causal buffer effect.')
    for key,title in [('executed_services','Preventive services executed'),('unnecessary_rate_among_executed_services','Unnecessary service rate')]:
        add(title,f['maintenance'][key],'services' if key=='executed_services' else 'fraction','SYNTHETIC-MAINTENANCE · DIGITAL-TWIN-REALIZED',fpath,'maintenance.'+key,'Phase II-F final 2201–2206','Synthetic replacement model and 24-hour attribution horizon; no field reliability evidence.')
    for key,title in [('averted_within_24h','Strict matched avoided failures'),('undetermined_counterfactual','Undetermined attribution')]:
        add(title,f['maintenance']['attribution'][key],'cases','SYNTHETIC-MAINTENANCE · EVALUATION-ONLY',fpath,'maintenance.attribution.'+key,'Phase II-F final 2201–2206','Undetermined counterfactuals are not counted as avoided; no runtime failure guarantee.')
    for strategy in ('F0','F2'):
        add(strategy+' final feasibility',f['all_attempt_comparison'][strategy]['feasibility_rate'],'fraction','HELD-OUT DIGITAL-TWIN EVALUATION',fpath,'all_attempt_comparison.'+strategy+'.feasibility_rate','Phase II-F final 2201–2206','All 24 attempts retained, including furnace timing/continuation failures.')
        add(strategy+' production completion',f['all_attempt_comparison'][strategy]['completed_production_rate'],'fraction','DIGITAL-TWIN-REALIZED',fpath,'all_attempt_comparison.'+strategy+'.completed_production_rate','Phase II-F / all 24 attempts','All attempted days, including incomplete operating plans.')
        for kind,unit in [('bar_t','t/day'),('billet_t','t/day'),('total_kWh','kWh/day'),('IF_SEC_kWh_per_t','kWh/t liquid'),('physical_evaluation_tariff_cost_Rs','synthetic Rs/day')]:
            add(strategy+' '+kind,f['paired_statistics'][kind][strategy]['mean'],unit,'DIGITAL-TWIN-REALIZED · SYNTHETIC-TARIFF' if 'tariff' in kind else 'DIGITAL-TWIN-REALIZED',fpath,'paired_statistics.'+kind+'.'+strategy+'.mean','Phase II-F / 21 paired complete replays','Conditional paired mean; completion rate uses all attempts.')
        add(strategy+' represented corrective failures',f['final_fault_process_evaluation_only'][strategy]['fault_count'],'events','EVALUATION-ONLY · SYNTHETIC-MAINTENANCE',fpath,'final_fault_process_evaluation_only.'+strategy+'.fault_count','Phase II-F / 24 final fault processes','Represented simulator failures, including tapes for failed operating plans; not field reliability.')
        for kind in ('corrective_asset_downtime_hours','preventive_asset_downtime_hours','total_asset_downtime_hours'):
            stat=f['paired_statistics'].get(kind)
            if stat:add(strategy+' '+kind,stat[strategy]['mean'],'asset h / paired day','SYNTHETIC-MAINTENANCE · DIGITAL-TWIN-REALIZED',fpath,'paired_statistics.'+kind+'.'+strategy+'.mean','Phase II-F / 21 paired complete replays','Paired complete days only; preventive and corrective components reported separately.')
    return dict(version='deck_metrics_v1',metrics=rows,external_benchmarks='UCI and AI4I remain EXTERNAL/PUBLIC-BENCHMARK; no benchmark score is a simulated plant operating KPI.')
