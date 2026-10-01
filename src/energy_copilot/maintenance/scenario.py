"""Action-aware wear tape. All non-wear draws keep the frozen named RNG streams."""
from copy import deepcopy
import numpy as np
import pandas as pd
from energy_copilot.common import rng_streams,canonical_hash
from energy_copilot.sim.scenario import scenario as frozen_scenario
from .contracts import validate_actions,settings


def scenario(config,seed,days,maintenance_actions=(),maintenance_config=None):
    tape=frozen_scenario(config,seed,days)
    if not maintenance_actions:return tape
    mc=maintenance_config or settings();start=pd.Timestamp(config['start']);total=days*1440;step=config['clock_minutes']
    actions=validate_actions(maintenance_actions,mc,start,days)
    original_sha=tape['hash'];f=config['faults'];t=(np.arange(days*1440//step)+.5)*step
    for asset,stream in (('MILL_01','wear_mill'),('PMP_01','wear_pump')):
        chosen=[a for a in actions if a.asset_id==asset]
        if not chosen:continue
        rng=rng_streams(seed,[stream])[stream];wear=np.zeros(len(t));unavailable=[];events=[]
        age_start=0.;initial=f['initial_wear'];life=float(rng.uniform(*f['wear_days']))*1440;repair=float(rng.uniform(*f['repair_hours']))*60
        label='bearing_wear' if asset=='MILL_01' else 'impeller_wear'
        def fill(stop):
            sel=(t>=age_start)&(t<min(stop,total));wear[sel]=initial+(t[sel]-age_start)/life
        def draw_next():
            return float(rng.uniform(*f['wear_days']))*1440,float(rng.uniform(*f['repair_hours']))*60
        for action in chosen:
            begin=(pd.Timestamp(action.start_time)-start).total_seconds()/60
            while age_start+(1-initial)*life<=begin:
                failure=age_start+(1-initial)*life
                if begin<failure+repair:raise ValueError('Preventive service overlaps corrective repair; intervention too late')
                fill(failure)
                unavailable.append((failure,failure+repair))
                events.extend((dict(asset_id=asset,start_min=failure,end_min=failure+repair,type='failure',label=label),
                               dict(asset_id=asset,start_min=failure,end_min=failure+repair,type='repair',label=f'{label}_replacement')))
                age_start=failure+repair;initial=0.;life,repair=draw_next()
            if begin<age_start:raise ValueError('Preventive service precedes asset recovery')
            fill(begin);held=initial+(begin-age_start)/life
            service_end=begin+action.duration_min
            restart_end=service_end+mc['service'][asset]['restart_delay_min']
            wear[(t>=begin)&(t<restart_end)]=held
            unavailable.append((begin,restart_end))
            events.append(dict(asset_id=asset,start_min=begin,end_min=service_end,type='preventive_service',label='SYNTHETIC-MAINTENANCE/reset_wear'))
            if restart_end>service_end:events.append(dict(asset_id=asset,start_min=service_end,end_min=restart_end,type='preventive_restart',label='SYNTHETIC-MAINTENANCE/restart_delay'))
            age_start=restart_end;initial=mc['service'][asset]['post_service_wear'];life,repair=draw_next()
        while age_start<total:
            failure=age_start+(1-initial)*life
            fill(min(failure,total))
            if failure>=total:break
            unavailable.append((failure,failure+repair))
            events.extend((dict(asset_id=asset,start_min=failure,end_min=failure+repair,type='failure',label=label),
                           dict(asset_id=asset,start_min=failure,end_min=failure+repair,type='repair',label=f'{label}_replacement')))
            age_start=failure+repair;initial=0.;life,repair=draw_next()
        tape['wear'][asset]=wear;tape['repairs'][asset]=sorted(unavailable)
        tape['events']=[e for e in tape['events'] if e['asset_id']!=asset]+events
    tape['maintenance_actions']=[dict(asset_id=a.asset_id,start_time=a.start_time,duration_min=a.duration_min,
                                      intervention_type=a.intervention_type,condition_effect=a.condition_effect) for a in actions]
    tape['original_exogenous_sha256']=original_sha
    identity={k:({a:v.tolist() for a,v in value.items()} if k=='wear' else value.tolist() if isinstance(value,np.ndarray) else value)
              for k,value in tape.items() if k!='hash'}
    tape['hash']=canonical_hash(identity)
    return tape
