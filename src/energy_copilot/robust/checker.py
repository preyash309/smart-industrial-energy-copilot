"""Independent scenario ledger: no optimizer expressions or coefficient helper imports."""
import math
from datetime import datetime
from .remaining_checker import check_schedule


def check_robust(inp,result,policy,scenarios):
    nominal=check_schedule(inp,result);errors=list(nominal['violations']);checks=[]
    origin=datetime.fromisoformat(inp.forecast_origin);c=inp.constraints;n=c.horizon_slots;tol=c.tolerance
    lookup={k.candidate_id:k.prediction for k in inp.heat_candidates}
    for s in scenarios:
        inv=inp.initial_inventory_t;arrivals=list(getattr(inp,'known_arrivals',()) or [0.0]*(n+1));power=[False]*n;previous=None;last=0;local=[]
        for pos,row in enumerate(result.schedule):
            p=lookup[row['candidate_id']];q=90 if s.use_upper_quantiles else (50 if inp.optimization_mode=='central' else 90)
            energy=getattr(p,f'energy_p{q}_kWh');duration=getattr(p,f'duration_p{q}_min')
            if s.residual_min:duration=max(duration,p.duration_p50_min+s.residual_min[pos])
            duration=max(duration,energy/c.ratings_kW['IF_01']*60+c.if_nonpowered_min)
            start=(datetime.fromisoformat(row['start'])-origin).total_seconds()/60;end=start+duration
            if previous is not None and start<previous-tol:local.append('scenario overlap/buffer')
            previous=math.ceil((end-tol)/c.candidate_step_minutes)*c.candidate_step_minutes+policy.buffer(p);last=end
            if end>n*15-policy.end_margin_min+tol:local.append('scenario end reserve')
            release=math.ceil((end-tol)/15)
            if not 1<=release<=n:local.append('out of horizon');continue
            arrivals[release]+=inp.heats[pos].liquid_t*c.cast_yield
            powerstart=end-energy/c.ratings_kW['IF_01']*60
            for t in range(n):
                if min(end,(t+1)*15)>max(start,t*15)+tol:
                    if not(inp.equipment_availability['IF_01'][t] and inp.operating_windows['IF_01'][t]):local.append('IF availability')
                if min(end,(t+1)*15)>max(powerstart,t*15)+tol:power[t]=True
        for t,row in enumerate(result.load_trajectory):
            r=row['rolling_billet_t'];states=row['asset_run'];aux=getattr(inp.background_load_forecast[t],f'load_p{90 if s.use_upper_quantiles or inp.optimization_mode=="conservative" else 50}_kW')
            bound=(c.ratings_kW['IF_01']*power[t]/c.power_factors['IF_01']+c.ratings_kW['MILL_01']*states['MILL_01']/c.power_factors['MILL_01']+
                   c.ratings_kW['CMP_01']*states['CMP_01']/c.power_factors['CMP_01']+
                   c.ratings_kW['RHF_01']*states['RHF_01']/c.power_factors['RHF_01']+c.ratings_kW['PMP_01']*states['PMP_01']/c.power_factors['PMP_01']+aux/c.power_factors['AUX'])
            if power[t] and not states['PMP_01']:local.append('cooling')
            if bound>c.demand_limit_kVA+tol:local.append('demand')
            if r>inv+tol:local.append('unavailable billets')
            if inv+arrivals[t+1]>c.inventory_max_t+tol:local.append('upper inventory')
            inv=inv-r+arrivals[t+1]
            if not c.inventory_min_t-tol<=inv<=c.inventory_max_t+tol:local.append('inventory')
        if inv<inp.production_order.final_inventory_min_t-tol:local.append('closing stock')
        checks.append(dict(scenario=s.name,feasible=not local,violations=local,end_reserve_min=n*15-last))
        errors.extend(s.name+': '+x for x in local)
    # Policy applies even when there is no uncertainty scenario.
    if not scenarios:
        for a,b in zip(result.schedule,result.schedule[1:]):
            p=lookup[a['candidate_id']]
            gap=(datetime.fromisoformat(b['start'])-datetime.fromisoformat(a['reserved_end'])).total_seconds()/60
            if gap+tol<policy.buffer(p):errors.append('nominal buffer')
        if result.schedule and (datetime.fromisoformat(result.schedule[-1]['predicted_end'])-origin).total_seconds()/60>n*15-policy.end_margin_min+tol:errors.append('nominal reserve')
    return dict(feasible=not errors,violations=errors,nominal=nominal,scenario_checks=checks)
