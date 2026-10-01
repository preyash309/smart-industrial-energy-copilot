"""Critical values and explanation sentences are constructed only from receipts."""
from .contracts import *

LIMITATIONS=('Reduced-order simulated plant; no field safety or reliability evidence.',
 'Synthetic electricity tariff; no real maintenance cost or ROI.',
 'Synthetic maintenance does not resolve furnace-duration/scheduling failures.',
 'Health risk is a calibrated simulated 24-hour probability.',
 'Replay acceptance is scenario-specific, not a guarantee for future operations.')


def packet(request,state,registry,outcome,reason):
    plan=state.get('plan');replay=state.get('replay');check=state.get('check')
    verified=outcome in ('VERIFIED_RECOMMENDATION','VERIFIED_ANALYSIS')
    if verified and not(plan and plan.optimizer_feasible and replay and replay.physically_valid and check and check.passed and
                        plan.schedule_id==replay.schedule_id==check.schedule_id and replay.replay_id==check.replay_id):
        raise BoundaryError('Unverified operating recommendation')
    values=[];sentences=[]
    for name,response,ref,fields,label in [
        ('predicted',plan,state.get('plan_ref'), [('energy','predicted_energy_kWh','kWh'),('tariff cost','predicted_cost_Rs','synthetic Rs'),
            ('peak demand','predicted_peak_kVA','kVA'),('IF SEC','predicted_SEC','kWh/t'),('production target','production_target_t','t')],'OPTIMIZER-PREDICTED'),
        ('replay',replay,state.get('replay_ref'), [('energy','realized_energy_kWh','kWh'),('tariff cost','realized_cost_Rs','synthetic Rs'),
            ('peak demand','realized_peak_kVA','kVA')],'DIGITAL-TWIN-REALIZED')]:
        if response is None or ref is None:continue
        for title,field,unit in fields:
            value=getattr(response,field)
            if value is None:continue
            registry.grounded(ref,field,value)
            values.append(GroundedValue(name+' '+title,value,unit,label,ref.response_id,field))
            sentences.append((f'{label}: {title} {value:.4f} {unit}.',(ref.response_id,)))
    recommendation=('Plan passed independent verification; no operating change is recommended in VERIFY mode.' if outcome=='VERIFIED_ANALYSIS' else
                    'Request operator review of the independently accepted deterministic '+plan.mode+' plan.' if verified else
                    'No operating change is recommended.' if outcome=='NO_ACTION_NEEDED' else 'NO VERIFIED RECOMMENDATION: '+reason)
    refs=tuple(registry.evidence.values())
    # Failed/unavailable services still have a traceable trusted gate receipt.
    if registry.audit.records:
        gate_hash=digest(dict(outcome=outcome,reason=reason,evidence=[primitive(r) for r in refs]))
        refs+=(EvidenceRef('supervisory_gate','gate_'+gate_hash[:24],gate_hash),)
    config_hash=state['config_hash']
    refs+=(EvidenceRef('supervisor_config','config_'+config_hash[:24],config_hash),)
    from pathlib import Path
    import hashlib
    protected=Path('configs/phase2g_readonly_manifest.json')
    protected_hash=hashlib.sha256(protected.read_bytes()).hexdigest()
    refs+=(EvidenceRef('upstream_config_and_release_hashes','upstream_'+protected_hash[:24],protected_hash),)
    all_ids=tuple(r.response_id for r in refs)
    sentences.insert(0,(recommendation,all_ids))
    if plan and plan.maintenance_actions:
        text='The maintenance-aware optimizer selected a preventive window under the configured SYNTHETIC-MAINTENANCE policy; this is not a promise to prevent failure.'
        sentences.append((text,(state['plan_ref'].response_id,)))
    else:sentences.append(('No preventive service selected.',all_ids))
    if verified:sentences.append(('Production, demand, inventory, cooling and independent physical checks: PASS.',(state['check_ref'].response_id,)))
    if state.get('comparison'):
        comp=state['comparison'];ref=state['comparison_ref']
        for title,field,unit in [('matched energy change','energy_delta_kWh','kWh'),('matched synthetic tariff change','cost_delta_Rs','synthetic Rs')]:
            v=getattr(comp,field)
            if v is not None:
                registry.grounded(ref,field,v);values.append(GroundedValue(title,v,unit,'DIGITAL-TWIN-REALIZED',ref.response_id,field))
                sentences.append((f'DIGITAL-TWIN-REALIZED: {title} {v:.4f} {unit}.',(ref.response_id,)))
    notes=('p50/p90 are empirical individual-outcome forecasts, not guaranteed joint safety bounds.',)
    if state.get('snapshot') and state['snapshot'].version=='scripted_fixture_v1':
        notes+=('SCRIPTED-TEST-DOUBLE: benchmark values are fabricated test fixtures, not plant replay evidence.',)
    d=dict(timestamp=request.timestamp,request=primitive(request),evidence=[primitive(r) for r in refs],outcome=outcome)
    return DecisionPacket('decision_'+digest(d)[:24],request.timestamp,'VERIFIED' if verified else 'PROPOSED',outcome,
        state.get('snapshot'),state.get('diagnostics'),state.get('predictions'),plan,replay,check,state.get('comparison'),
        tuple(state.get('alternatives',())),recommendation,tuple(values),notes,LIMITATIONS,
        'Operator approval required; execution disabled by default.' if verified else 'Review/escalate; no executable plan.',
        refs,tuple(sentences))
