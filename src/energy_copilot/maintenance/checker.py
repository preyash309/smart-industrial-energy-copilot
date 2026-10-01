"""Independent maintenance acceptance from replay tables and explicit actions."""
from dataclasses import asdict
import numpy as np
import pandas as pd
from energy_copilot.common import values
from .contracts import validate_actions,settings
from .replay_checker import verify_physics


def verify_maintenance(sim, day_input, actions, controls=None, maintenance_config=None, original_exogenous_sha256=None):
    cfg=maintenance_config or settings();c=values(sim.config);start=pd.Timestamp(c['start'])
    actions=validate_actions(actions,cfg,start,sim.scenario_manifest['days'])
    physical=verify_physics(sim,day_input,controls);checks=dict(physical['checks']);step=c['clock_minutes']
    site=sim.latent_truth[sim.latent_truth.asset_id.eq('MAIN')].set_index('timestamp')
    event=sim.events[sim.events.type.eq('preventive_service')]
    checks['synthetic_service_event_count']=abs(len(event)-len(actions))
    for i,action in enumerate(actions):
        begin=pd.Timestamp(action.start_time);end=pd.Timestamp(action.end_time)
        matching=event[event.asset_id.eq(action.asset_id)&event.start.eq(begin)&event.end.eq(end)]
        checks[f'service_{i}_event_exactly_once']=int(len(matching)!=1)
        select=site.loc[(site.index>=begin)&(site.index<end)]
        asset=sim.latent_truth[sim.latent_truth.asset_id.eq(action.asset_id)].set_index('timestamp').loc[select.index]
        checks[f'service_{i}_asset_unavailable']=int((select['mill_available_min' if action.asset_id=='MILL_01' else 'pump_available_min']>1e-8).sum())
        checks[f'service_{i}_power_off']=int((asset.kW>1e-8).sum())
        checks[f'service_{i}_state']=int((~asset.state.str.startswith('preventive_service')).sum())
        if action.asset_id=='MILL_01':checks[f'service_{i}_rolling_zero']=int((select.rolled_billet_t>1e-8).sum())
        else:
            checks[f'service_{i}_IF_power_zero']=int((select.if_powered_min>1e-8).sum())
            heats=sim.latent_heats
            checks[f'service_{i}_heat_nonoverlap']=int(((heats.start<end)&(heats.end>begin)).sum())
        restart=end+pd.Timedelta(minutes=cfg['service'][action.asset_id]['restart_delay_min'])
        first=sim.latent_truth[(sim.latent_truth.asset_id==action.asset_id)&sim.latent_truth.timestamp.ge(restart)].iloc[0]
        reset=cfg['service'][action.asset_id]['post_service_wear']
        first_elapsed=(pd.Timestamp(first.timestamp)-restart).total_seconds()/60+step/2
        # Independent bound from declared life range, no simulator wear stream.
        low=reset+first_elapsed/(c['faults']['wear_days'][1]*1440)
        high=reset+first_elapsed/(c['faults']['wear_days'][0]*1440)
        checks[f'service_{i}_single_wear_reset']=int(not low-1e-8<=first.latent_wear<=high+1e-8)
    if original_exogenous_sha256 is not None:
        h=sim.scenario_manifest.get('exogenous_scenario_sha256',sim.scenario_manifest['scenario_sha256'])
        checks['matched_original_exogenous_tape']=int(h!=original_exogenous_sha256)
    return dict(label='SYNTHETIC-MAINTENANCE-INDEPENDENT',feasible=not any(checks.values()),checks=checks,violations=sum(checks.values()),physical=physical,
                assumptions='Only the configured synthetic replacement resets wear; no future fault labels enter decisions.')
