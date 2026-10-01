"""Generate frozen coefficients through the public typed PredictionService only."""
from datetime import timedelta
from pathlib import Path
import math
import yaml
from energy_copilot.common import values, validate_parameters, sha256
from energy_copilot.forecast import PredictionService
from .contracts import ASSETS, HeatOrder, HeatCandidate, OperatingConstraints, OptimizerInput, timestamp


def load_settings(path='configs/optimizer_v1.yaml'):
    raw=yaml.safe_load(Path(path).read_text(encoding='utf-8'));validate_parameters(raw)
    cfg=values(raw)
    rawplant=yaml.safe_load(Path(cfg['plant_config']).read_text(encoding='utf-8'));validate_parameters(rawplant)
    p=values(rawplant)
    sections={'IF_01':'if','MILL_01':'mill','RHF_01':'rhf','PMP_01':'pump','CMP_01':'compressor','AUX':'aux'}
    ratings={a:p[s]['rated_kw' if a=='IF_01' else 'electric_kw' if a=='RHF_01' else 'rating_kw'] for a,s in sections.items() if a!='AUX'}
    c=OperatingConstraints(cfg['slot_minutes'],cfg['horizon_slots'],cfg['candidate_step_minutes'],
        p['acceptance']['contract_kva'],p['material']['yard_min'],p['material']['yard_max'],
        p['material']['cast_yield'],p['material']['rolling_yield'],p['if']['melt_yield'],
        p['mill']['capacity_tph'],p['rhf']['capacity_tph'],p['mill']['sec'],p['if']['nonpowered_min'],
        p['rhf']['temp'],p['rhf']['temp_min'],p['rhf']['temp_max'],ratings,
        {a:p[s]['pf'] for a,s in sections.items()},p['compressor']['loaded_kw'],p['compressor']['idle_kw'],
        tuple(cfg['allowed_practices']),cfg['sec_target'],cfg['tolerance'],cfg['solver'])
    return cfg,p,c


def build_optimizer_input(service,forecast_origin,production_order,initial_inventory_t,heats,
                          heat_history,load_context,tariff_calendar,tariff_period_rates,
                          tariff_version,tariff_source,equipment_availability,operating_windows,
                          health_contexts=(),mode='central',objective='feasibility',settings='configs/optimizer_v1.yaml'):
    if not isinstance(service,PredictionService): raise TypeError('Public PredictionService required')
    cfg,plant,c=load_settings(settings)
    if service.contract['version']!=cfg['prediction_version']: raise ValueError('Prediction contract version mismatch')
    if sha256(service.directory/'prediction_contract.json')!=cfg['prediction_contract_sha256']:
        raise ValueError('Prediction contract mismatch')
    schema=sha256(service.directory/'prediction_schema.yaml')
    if schema!=cfg['prediction_schema_sha256']: raise ValueError('Prediction schema mismatch')
    if not set(c.supported_practices)<=set(service.contract['practice_modes']): raise ValueError('Unqualified practice')
    origin=timestamp(forecast_origin); candidates=[]
    history=dict(heat_history['features']);ats=dict(heat_history['available_at'])
    if set(history)!={'previous_heat_SEC','previous_heat_duration','rolling_mean_SEC','global_mean_SEC','historical_duration_mean','context_PMP_01_flow_m3_h','context_MILL_01_vibration_mm_s'}:
        raise ValueError('Heat history schema mismatch')
    # Cache equal predictor envelopes within an hour. All 12 features are identical;
    # start minute and heat ID are metadata, not model features. Never infer E/D here.
    for h in heats:
        if h.liquid_t!=service.contract['candidate_liquid_t']: raise ValueError('Unsupported liquid batch size')
        cache={}
        for minute in range(0,c.horizon_slots*c.slot_minutes,c.candidate_step_minutes):
            start=origin+timedelta(minutes=minute)
            for practice in c.supported_practices:
                key=(start.hour,practice)
                if key not in cache:
                    f=dict(history,hour=start.hour,weekday=start.weekday(),shift=start.hour//8,
                           practice_loss_kWh_t=service.contract['practice_modes'][practice]['practice_loss_kWh_t'],candidate_liquid_t=h.liquid_t)
                    posting=dict(ats,**{k:origin.isoformat() for k in ('hour','weekday','shift','practice_loss_kWh_t','candidate_liquid_t')})
                    cache[key]=service.predict_heat(dict(heat_id=h.heat_id,forecast_origin=origin.isoformat(),candidate_start=start.isoformat(),features=f,available_at=posting),practice)
                candidates.append(HeatCandidate(f'{h.heat_id}:{minute}:{practice}',h.heat_id,start.isoformat(),cache[key]))
    background=tuple(service.predict_background_load(origin.isoformat(),c.horizon_slots,load_context))
    health=tuple(service.predict_health(ctx,service.contract['health_horizon_hours']) for ctx in health_contexts)
    return OptimizerInput(origin.isoformat(),production_order,initial_inventory_t,tuple(heats),tuple(candidates),background,
        equipment_availability,operating_windows,tuple(tariff_calendar),tariff_period_rates,tariff_version,tariff_source,
        c,cfg['prediction_version'],schema,cfg['prediction_schema_sha256'],health,mode,objective).validate()


def coefficients(inp,practices=None):
    """Pre-solve reduction; physical constants come from the input config snapshot."""
    c=inp.constraints;origin=timestamp(inp.forecast_origin);suffix='50' if inp.optimization_mode=='central' else '90'
    allowed=set(c.supported_practices if practices is None else practices)
    if not allowed or not allowed<=set(c.supported_practices): raise ValueError('Unsupported practice subset')
    result={};by_heat={h.heat_id:[] for h in inp.heats}; total=c.horizon_slots*c.slot_minutes
    for k in inp.heat_candidates:
        if k.prediction.practice_mode not in allowed: continue
        p=k.prediction;start=(timestamp(k.start)-origin).total_seconds()/60
        duration=getattr(p,f'duration_p{suffix}_min');energy=getattr(p,f'energy_p{suffix}_kWh')
        end=start+duration; powered=energy/c.ratings_kW['IF_01']*60
        if duration+c.tolerance<powered+c.if_nonpowered_min:
            # Do not silently change a prediction into a physically inconsistent cycle.
            continue
        finish=math.ceil((end-c.tolerance)/c.candidate_step_minutes)*c.candidate_step_minutes
        if finish>total: continue
        occupied=tuple(range(int(start//c.slot_minutes),math.ceil((end-c.tolerance)/c.slot_minutes)))
        if any(not(inp.equipment_availability['IF_01'][t] and inp.operating_windows['IF_01'][t]) for t in occupied): continue
        power_start=end-powered; slot_energy={};power_slots=[]
        for t in occupied:
            overlap=max(0,min(end,(t+1)*c.slot_minutes)-max(power_start,t*c.slot_minutes))
            if overlap>c.tolerance:
                if not(inp.equipment_availability['PMP_01'][t] and inp.operating_windows['PMP_01'][t]): break
                power_slots.append(t);slot_energy[t]=overlap/60*c.ratings_kW['IF_01']
        else:
            result[k.candidate_id]=dict(candidate=k,start=start,end=end,reserved_end=finish,duration=duration,energy=energy,
                slot_energy=slot_energy,power_slots=tuple(power_slots),release_boundary=math.ceil((end-c.tolerance)/c.slot_minutes),
                micro_slots=tuple(range(int(start/c.candidate_step_minutes),int(finish/c.candidate_step_minutes))))
            by_heat[k.heat_id].append(k.candidate_id)
    if any(not ks for ks in by_heat.values()): return {},by_heat
    # Preserve ordered heat sequence (the same heat identities feed later replay).
    mins={h:min(result[k]['reserved_end']-result[k]['start'] for k in ks) for h,ks in by_heat.items()}
    before=0
    for i,h in enumerate(inp.heats):
        after=sum(mins[x.heat_id] for x in inp.heats[i:])
        kept=[k for k in by_heat[h.heat_id] if result[k]['start']>=before-c.tolerance and result[k]['start']<=total-after+c.tolerance]
        by_heat[h.heat_id]=kept; before+=mins[h.heat_id]
    keep={k for ks in by_heat.values() for k in ks}
    return {k:v for k,v in result.items() if k in keep},by_heat
