"""Seven thin screens. Plant decisions and metrics come from DashboardService."""
import json
import streamlit as st
from . import charts as ch
from .components import metric_cards,plot,card,flow,badge

def fmt(v,d=1):return 'Unavailable' if v is None else f'{v:,.{d}f}'
def frame(rows,columns=None):
    if not rows:st.info('No released observations available for this case. No values are borrowed from another scenario.');return
    st.dataframe([{k:r.get(k) for k in columns} for r in rows] if columns else rows,width='stretch',hide_index=True)

def overview(s):
    v=s.get_overview();st.subheader('See the plant. Know what needs attention.')
    st.caption(v['label']+' · Day outcomes below are replay evidence, not observations available at the midnight decision.')
    metric_cards([(v['production_label'],fmt(v['production_t'])+' t','bars'),('Electricity',fmt(v['electricity_kWh']/1000 if v['electricity_kWh'] is not None else None)+' MWh','electricity'),
        ('IF specific energy',fmt(v['SEC'])+' kWh/t','liquid steel'),('Peak demand',fmt(v['peak_kVA'],0)+' kVA','Selected forecast bound or independently checked physical peak'),
        ('Synthetic electricity cost','Rs '+fmt(v['cost_Rs'],0),'SYNTHETIC-TARIFF'),('Observable candidates',str(v['alert_count']),'Rules + frozen policy eligibility, not confirmed faults')])
    st.markdown('')
    if v['verified']:card('Verified plan ready for operator review',s.packet['recommendation'])
    else:card('No verified recommendation',s.packet['recommendation'],True)
    a,b=st.columns([1.6,1])
    e=s.get_energy_view()
    with a:
        st.subheader('Plant load')
        if e['replay_observations']:plot(ch.load(e['replay_observations']));st.caption('Replay-day QC public MAIN measurements; gaps are retained.')
        elif e['observed_history']:plot(ch.load(e['observed_history']));st.caption('Completed historical intervals available at decision time.')
        else:st.info('Only the released public snapshot is available for this rejected episode.')
    with b:
        st.subheader('Where electricity goes')
        if e['asset_energy']:plot(ch.assets(e['asset_energy']));st.caption('Public feeder estimates; noisy/missing meters need not close exactly to physical MAIN.')
        else:frame([{'Asset':k,'Predicted kWh':v} for k,v in s.bundle['schedule']['metrics'].get('asset_kWh',{}).items()])
    st.subheader('Process at a glance');flow(s.bundle['metadata']['maintenance_eligible_assets'])
    a,b=st.columns([1.4,1])
    with a:
        st.subheader('Recent completed heats');frame(e['heat_analytics'][-5:],['heat_id','SEC_kWh_per_t','duration_min'])
    with b:
        st.subheader('24-hour predictive health risk')
        frame([{'Asset':r['asset_id'],'Calibrated 24h risk':f"{r['calibrated_probability']:.1%}"} for r in v['predictions']['health_risk']])
        st.caption('Risk is predictive; it is not an exact failure-time estimate.')

def energy(s):
    e=s.get_energy_view();st.subheader('Where energy goes — and where to investigate')
    st.caption('Observable analytics from this run only. Diagnostics suggest candidates, not confirmed causes or avoidable savings.')
    if e['replay_observations']:plot(ch.load(e['replay_observations']))
    elif e['observed_history']:plot(ch.load(e['observed_history']))
    else:st.info('No completed public meter trace was released for this rejected run.')
    a,b=st.columns([1.4,1])
    with a:
        st.subheader('Expected vs actual heat electricity')
        if e['heat_analytics']:plot(ch.expected_actual(e['heat_analytics']))
        else:st.info('Heat completion analytics unavailable; predictions do not substitute for actual outcomes.')
    with b:
        st.subheader('Specific-energy distribution')
        if e['heat_analytics']:plot(ch.sec_distribution(e['heat_analytics']))
    if e['heat_analytics']:
        h=max((r for r in e['heat_analytics'] if r['expected_kWh']),key=lambda r:r['residual_SEC'],default=None)
        if h:st.caption(f"{h['heat_id']}: actual {fmt(h['kWh'])} kWh; historical expectation {fmt(h['expected_kWh'])} kWh. SEC residual {fmt(h['residual_SEC'])} kWh/t. Causality is not established.")
    st.subheader('Evidence-based diagnostic candidates');frame(e['diagnostics'],['asset_id','rule','measured_value','expected_value','unit','confidence','possible_cause'])
    st.caption('Tariff shifting changes cost exposure. It does not, by itself, reduce energy.')
    with st.expander('Decision-time forecasts — heat energy, duration and AUX'):
        predictions=s.packet['predictions']
        frame(predictions['heat_estimates'],['heat_id','energy_p50_kWh','energy_p90_kWh','duration_p50_min','duration_p90_min','available_at'])
        plot(ch.background(predictions))
        st.caption('Frozen PredictionService forecasts posted at '+predictions['available_at']+'. AUX is background only; controlled loads are constructed by the optimizer. p90 is an upper empirical quantile, not a guarantee.')

def optimise(s):
    v=s.get_schedule_comparison();p=s.packet['optimizer_plan'];st.subheader('A stronger plan — checked before release')
    st.caption('Low tariff = green shading · normal = grey · high = amber. SYNTHETIC-TARIFF, not an actual utility bill.')
    metric_cards([('Predicted energy',fmt(p['predicted_energy_kWh']/1000)+' MWh','OPTIMIZER-PREDICTED'),('Predicted synthetic cost','Rs '+fmt(p['predicted_cost_Rs'],0),'OPTIMIZER-PREDICTED / SYNTHETIC-TARIFF'),
        ('Predicted peak bound',fmt(p['predicted_peak_kVA'],0)+' kVA','Empirical uncertainty assumptions, not guarantees'),('Production order',fmt(p['production_target_t'])+' t','Hard production requirement'),
        ('Required end reserve',fmt(p['reserve_minutes'])+' min','Frozen policy'),('Optimizer status',p['status'],'Feasible is not physically verified')])
    st.subheader('Current / reference operating sequence')
    if v['reference_schedule']:plot(ch.schedule(v['reference_schedule'],s.packet['timestamp'],v['predicted_trajectory'],reference=True));st.caption(v['reference_note'])
    else:st.info('Reference trace is unavailable for this rejected case; no different-run timeline is substituted.')
    st.subheader('Recommended candidate — optimizer-predicted')
    plot(ch.schedule(v['predicted_schedule'],s.packet['timestamp'],v['predicted_trajectory'],p['maintenance_actions']))
    if v['initial_rejected']:st.caption('Initial rejection retained. This is a verified adaptive control-policy recommendation; initial forecasts and realized dispatch are distinct.')
    plot(ch.rolling_and_inventory(v['predicted_trajectory']))
    plot(ch.inventory(v['inventory']))
    st.caption('Rolling activity is planned billet feed. Inventory constraints are independently checked; the initial prediction is not a future truth trajectory.')
    card('Independent digital-twin gate',s.packet['replay_outcome']['status']+' · '+(s.packet['replay_outcome'].get('failure_reason') or 'All represented physical checks passed.'),not s.packet['replay_outcome']['physically_valid'])

def maintenance(s):
    v=s.get_maintenance_view();st.subheader('Predictive risk. Frozen policy. Verified service.')
    st.caption('SYNTHETIC-MAINTENANCE · A calibrated 24-hour probability is not a time-to-failure prediction.')
    cols=st.columns(2)
    for col,r in zip(cols,v['health']):
        with col:
            st.metric(r['asset_id']+' · 24h risk',f"{r['calibrated_probability']:.1%}")
            st.caption('Frozen policy eligible' if r['asset_id'] in v['eligibility'] else 'No eligible service candidate at this snapshot')
            if v['history']:plot(ch.health(v['history'],r['asset_id']))
            else:frame([{'Observed channel':r0['field'],'Value':r0['value'],'Posted at':r0['available_at']} for r0 in v['observations'] if r0['asset_id']==r['asset_id'] and r0['field'] in ('vibration_mm_s','temp_C')])
    st.subheader('Preventive service disposition')
    if v['initial_selected']:
        frame(v['initial_selected'],['asset_id','start_time','duration_min','policy_version'])
        card('Selected in the initial candidate','Replay accepted the service plan.' if v['verified'] else 'The candidate was rejected. These windows are recommendations, not performed maintenance actions.',not v['verified'])
    else:st.info('No preventive service selected by the deterministic optimizer.')
    st.caption('Eligibility, sensor-quality gate, service duration and wear intervention come from the frozen Phase II-F policy. The dashboard adds no thresholds. Matched avoided-failure attribution is evaluation-only and appears on Impact, never as a current diagnosis.')

def decision_center(s):
    p=s.get_decision_packet();good=p['outcome']=='VERIFIED_RECOMMENDATION';st.subheader('Decision Center')
    title='REJECTED BY OPERATOR' if s.status=='REJECTED' else 'APPROVED · SIMULATION ONLY' if s.status=='APPROVED' else 'VERIFIED RECOMMENDATION' if good else 'NO VERIFIED RECOMMENDATION'
    card(title,p['recommendation'],not good or s.status=='REJECTED')
    st.caption(s.bundle['metadata']['scope']+' · VERIFIED ≠ APPROVED · Current disposition: '+s.status)
    a,b=st.columns(2)
    with a:
        st.markdown('**Optimizer-predicted**');plan=p['optimizer_plan']
        frame([{'Metric':'Electricity','Value':fmt(plan['predicted_energy_kWh'])+' kWh'},{'Metric':'Synthetic tariff cost','Value':'Rs '+fmt(plan['predicted_cost_Rs'])},
            {'Metric':'Peak kVA bound','Value':fmt(plan['predicted_peak_kVA'])+' kVA'}])
    with b:
        st.markdown('**Independent replay**');r=p['replay_outcome']
        if good:
            frame([{'Check':k.replace('_',' ').title(),'Result':'PASS' if v else 'FAIL'} for k,v in p['independent_check']['checks']])
        else:
            st.error(r['status']+' — '+(r.get('failure_reason') or 'Physical acceptance evidence is missing.'))
            st.write('Optimizer feasibility does not imply physical feasibility. Recommendation withheld.')
    st.markdown('**Maintenance**');st.write('Selected preventive window; subject to verified plan and explicit approval.' if plan['maintenance_actions'] else 'No preventive service selected in this candidate.')
    st.markdown('**Main remaining risk**');st.write('Heat-duration uncertainty can consume schedule reserve. Empirical upper quantiles are not safety guarantees.')
    st.markdown('**Required action**');st.write('Operator review. This prototype controls no machinery and simulated execution is disabled in the UI.')
    terminal=s.status in ('APPROVED','REJECTED','EXECUTED')
    with st.form('operator_feedback_'+s.session_id):
        confirmed=st.checkbox('I explicitly approve this verified simulated plan for the demo audit.',disabled=not good or terminal,key='confirmation_'+s.session_id)
        reason=st.text_input('Review note (optional)')
        a,b,c=st.columns(3)
        approved=a.form_submit_button('Approve',disabled=not good or terminal,type='primary')
        rejected=b.form_submit_button('Reject',disabled=terminal)
        deferred=c.form_submit_button('Defer',disabled=terminal)
        try:
            if approved:s.approve_decision(confirmed,reason);st.success('Approval recorded. No real equipment or simulation was executed.');st.rerun()
            elif rejected:s.reject_decision(reason);st.rerun()
            elif deferred:s.defer_decision(reason);st.info('Deferred; verification status retained. Operator feedback is audited.');st.rerun()
        except ValueError as exc:st.error(str(exc))
    if s.last_feedback:st.caption('Latest recorded operator action: '+s.last_feedback)
    with st.expander('Energy Copilot — grounded explanation'):
        st.write(p['recommendation'])
        for sentence,refs in p['card_sentences'][:6]:st.write(sentence)
        st.caption('Deterministic G0 explanation. No chatbot or live LLM. Detailed provenance is on Evidence / Audit.')

def impact(s):
    metrics=s.get_impact_summary()['metrics'];by={r['metric']:r for r in metrics}
    st.subheader('Impact, separated by mechanism')
    st.info('Historical release evidence below is a separate evaluation population, not today’s selected scenario. No field savings are claimed.')
    st.markdown('**Phase II-D · matched seed-42 experiment**')
    a,b=st.columns(2)
    a.metric('Simulated electricity reduction',fmt(by['Matched electricity reduction']['value'],2)+'%')
    b.metric('Synthetic tariff reduction',fmt(by['Matched synthetic tariff reduction']['value'],2)+'%')
    st.caption('DIGITAL-TWIN-REALIZED · SYNTHETIC-PRACTICE · SYNTHETIC-TARIFF. These are distinct effects in one matched experiment.')
    st.markdown('**Phase II-E · held-out scheduling robustness**')
    a,b=st.columns(2)
    a.metric('Original E0 scheduler',str(by['E0 final feasible cases']['value'])+' / 10 feasible')
    b.metric('Robust adaptive E4',str(by['E4 final feasible cases']['value'])+' / 10 feasible')
    st.caption('Held-out digital-twin final seeds 201–210; a combined scheduling-policy comparison, not a rare-event safety certification.')
    st.markdown('**Phase II-F · maintenance trade-off**')
    metric_cards([('Executed preventive services',str(by['Preventive services executed']['value']),'SYNTHETIC-MAINTENANCE'),
        ('Strict matched avoided failures',str(by['Strict matched avoided failures']['value']),'EVALUATION-ONLY / matched counterfactual'),
        ('Undetermined attribution',str(by['Undetermined attribution']['value']),'Not counted as avoided failures'),
        ('Unnecessary within 24 h',f"{by['Unnecessary service rate']['value']:.0%}",'Rate among executed services; no claim about longer-term value'),
        ('F0 final schedule feasibility',f"{by['F0 final feasibility']['value']:.2%}",'22 / 24 attempts'),
        ('F2 maintenance feasibility',f"{by['F2 final feasibility']['value']:.2%}",'21 / 24 attempts')])
    st.warning('Maintenance removed represented corrective failures, but did not improve overall final scheduling feasibility. Furnace-duration failures remained.')
    st.subheader('Preventive and corrective downtime — kept separate')
    frame([{'Strategy':'No preventive service' if r['metric'].startswith('F0') else 'Preventive service',
        'Downtime component':r['metric'].split(' ',1)[1].replace('_',' '),'Mean asset hours / paired day':r['value']} for r in metrics if 'asset_downtime_hours' in r['metric']])
    st.caption('21 paired complete replays. Production completion is reported over all 24 attempts; completed-day averages are conditional. No validated industrial maintenance cost or ROI exists.')
    st.subheader('Separate production, electricity and synthetic tariff outcomes')
    frame([{'Metric':r['metric'],'Value':r['value'],'Unit':r['unit']} for r in metrics if any(k in r['metric'] for k in ('production completion','bar_t','billet_t','total_kWh','IF_SEC_kWh_per_t','physical_evaluation_tariff_cost_Rs','represented corrective failures'))])
    with st.expander('Deck-approved metrics with provenance'):frame(metrics,['metric','value','unit','evidence_label','scenario','source_artifact','caveat'])
    st.caption('UCI Steel and AI4I are separate PUBLIC-BENCHMARK datasets, not reference-plant operating measurements.')

def evidence(s):
    e=s.get_evidence();p=e['packet'];st.subheader('Evidence / Audit')
    st.caption('Trace the recommendation to typed services, matched replay and the independent checker.')
    rows=[('Decision ID',p['decision_id']),('Snapshot ID',p['snapshot']['snapshot_id']),('Model version',p['predictions']['model_version']),
        ('Feature schema hash',p['predictions']['schema_sha256']),('Optimizer version',p['optimizer_plan']['optimizer_version']),
        ('Schedule ID',p['optimizer_plan']['schedule_id']),('Replay ID',p['replay_outcome']['replay_id']),
        ('Independent checker','PASS · '+p['independent_check']['checker_id'] if p['independent_check'] else 'NO ACCEPTED CHECK'),
        ('Maintenance policy','maintenance_v1 · frozen'),('Approval status',e['approval_status']),('Dashboard session',e['session_id']),
        ('Evidence scope',e['metadata']['scope']),('Seed / day',str(e['metadata']['seed'])+' / '+str(e['metadata']['day']))]
    frame([{'Field':k,'Value':v} for k,v in rows])
    with st.expander('Config and provenance hashes'):frame(p['provenance'])
    with st.expander('Raw DecisionPacket'):st.json(p)
    st.download_button('Download DecisionPacket',json.dumps(p,indent=2),file_name=p['decision_id']+'.json',mime='application/json')
    st.caption('Hidden plant truth, fault tape and future measurements are not available to dashboard decisions. Post-replay outcomes are explicitly labelled evaluation evidence.')

RENDERERS={'Overview':overview,'Energy':energy,'Optimise':optimise,'Maintenance':maintenance,'Decision Center':decision_center,'Impact':impact,'Evidence / Audit':evidence}
