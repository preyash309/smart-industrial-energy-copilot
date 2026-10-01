"""Independent arithmetic/event ledger. Imports no model/coefficient/solver code."""
from datetime import timedelta
from dataclasses import asdict
import math
from .contracts import ASSETS, timestamp


def check_schedule(inp,result):
    """Check a proposed plan, including ALL reported trajectories and metrics."""
    errors=[]
    try:
        inp.validate()
        return _check(inp,result,errors)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as e:
        return dict(feasible=False,violations=errors+[f'Malformed plan: {e}'])


def _check(inp,result,errors):
    c=inp.constraints;tol=c.tolerance;n=c.horizon_slots;dt=c.slot_minutes/60;origin=timestamp(inp.forecast_origin)
    def require(ok,why):
        if not ok:errors.append(why)
    def close(a,b,why):
        require(isinstance(a,(int,float)) and not isinstance(a,bool) and math.isfinite(a) and abs(a-b)<=tol,why)
    require(result.status in ('optimal','feasible','baseline_feasible'),'Solver did not return a feasible status')
    require(result.optimization_mode==inp.optimization_mode and result.objective_mode==inp.objective_mode,'Result/input modes differ')
    require(result.forecast_origin==inp.forecast_origin,'Forecast origin altered')
    require(tuple(result.health_context)==tuple(asdict(p) for p in inp.health_predictions),'Health context altered')
    require(len(result.schedule)==len(inp.heats),'Wrong number of heats')
    candidates={k.candidate_id:k for k in inp.heat_candidates};orders={h.heat_id:h for h in inp.heats}
    selected={}; intervals=[];arrivals=[0.0]*(n+1);if_energy=[0.0]*n;on=[False]*n
    energy=0;occupied_minutes=0;reserved_minutes=0
    for row in result.schedule:
        require(set(row)=={'candidate_id','heat_id','start','selected_practice','predicted_end','reserved_end','energy_p50_kWh','energy_p90_kWh','duration_p50_min','duration_p90_min','selected_energy_kWh','selected_duration_min'},'Unknown/missing schedule fields')
        k=candidates[row['candidate_id']];p=k.prediction
        require(row['heat_id']==k.heat_id and k.heat_id not in selected,'Missing/duplicate/misidentified heat')
        selected[k.heat_id]=row
        require(row['selected_practice']==p.practice_mode,'Practice differs from prediction')
        require(row['start']==k.start,'Start differs from frozen candidate')
        for key in ('energy_p50_kWh','energy_p90_kWh','duration_p50_min','duration_p90_min'):
            close(row[key],getattr(p,key),'Heat quantile altered: '+key)
        q='50' if inp.optimization_mode=='central' else '90'
        duration=getattr(p,f'duration_p{q}_min');e=getattr(p,f'energy_p{q}_kWh')
        start=(timestamp(k.start)-origin).total_seconds()/60;end=start+duration
        close(row['selected_energy_kWh'],e,'Wrong selected energy quantile');close(row['selected_duration_min'],duration,'Wrong selected duration quantile')
        expected_end=origin+timedelta(minutes=end)
        require(abs((timestamp(row['predicted_end'])-expected_end).total_seconds())<=tol*60,'Wrong predicted end')
        reserve=math.ceil((end-tol)/c.candidate_step_minutes)*c.candidate_step_minutes
        require(timestamp(row['reserved_end'])==origin+timedelta(minutes=reserve),'Wrong duration reservation')
        require(0<=start<end<=n*c.slot_minutes+tol,'Heat outside horizon')
        intervals.append((start,end,reserve,k.heat_id));energy+=e;occupied_minutes+=duration;reserved_minutes+=reserve-start
        # Independent integration of a full-power tail in the predicted cycle.
        powered_minutes=e/c.ratings_kW['IF_01']*60;power_start=end-powered_minutes
        require(power_start-start>=c.if_nonpowered_min-tol,'Inconsistent forecast energy/duration cycle')
        release=int(math.ceil((end-tol)/c.slot_minutes));arrivals[release]+=orders[k.heat_id].liquid_t*c.cast_yield
        for t in range(n):
            lo=t*c.slot_minutes;hi=lo+c.slot_minutes
            busy=max(0,min(end,hi)-max(start,lo))
            if busy>tol:
                require(inp.equipment_availability['IF_01'][t] and inp.operating_windows['IF_01'][t],f'IF window/availability violation {t}')
            minutes=max(0,min(end,hi)-max(power_start,lo))
            if minutes>tol:on[t]=True
            if_energy[t]+=minutes*c.ratings_kW['IF_01']/60
    require(set(selected)==set(orders),'Each ordered heat must appear exactly once')
    intervals.sort()
    require([x[3] for x in intervals]==[h.heat_id for h in inp.heats],'Heat order changed')
    for left,right in zip(intervals,intervals[1:]):
        require(right[0]>=left[1]-tol,'Furnace overlap')
        require(right[0]>=left[2]-tol,'Rounded reservation overlap')
    close(sum(if_energy),energy,'Slot furnace energy does not sum to heat energy')
    require(len(result.load_trajectory)==n and len(result.inventory_trajectory)==n+1,'Trajectory length mismatch')
    inventory=inp.initial_inventory_t;stock=[inventory];total=0;cost=0;bar=0;peak_bound=0;peak_avg=0;peak_kw=0;asset_totals={a:0.0 for a in ASSETS+('AUX',)}
    running={a:0 for a in ASSETS};binding=[];minstock=inventory;maxstock=inventory
    for t,row in enumerate(result.load_trajectory):
        require(set(row)=={'slot','interval_start','interval_end','asset_run','furnace_on','pump_on','asset_kWh','total_kWh','total_kW','average_kVA','kVA_bound','rolling_billet_t','bar_t','billet_arrival_t','rhf_temperature_C','tariff_Rs_per_kWh','tariff_period','tariff_cost_Rs'},'Unknown/missing slot fields')
        require(row['slot']==t,'Trajectory slot order')
        require(timestamp(row['interval_start'])==origin+timedelta(minutes=t*c.slot_minutes),'Slot timestamp mismatch')
        require(timestamp(row['interval_end'])==origin+timedelta(minutes=(t+1)*c.slot_minutes),'Slot end mismatch')
        r=row['rolling_billet_t'];require(isinstance(r,(int,float)) and math.isfinite(r) and r>=-tol,'Invalid rolling tonnes')
        states=row['asset_run'];require(set(states)==set(ASSETS),'Wrong state assets')
        for a in ASSETS:
            require(type(states[a]) is bool,'Nonbinary asset state')
            require(not states[a] or (inp.equipment_availability[a][t] and inp.operating_windows[a][t]),f'{a} unavailable/calendar violation {t}')
            running[a]+=int(states[a])
        require(states['IF_01']==on[t] and row['furnace_on']==on[t],'Furnace power flag mismatch')
        require(row['pump_on']==states['PMP_01'],'Pump flags disagree')
        require(not on[t] or states['PMP_01'],f'Cooling interlock violation {t}')
        require(states['PMP_01']==bool(inp.equipment_availability['PMP_01'][t] and inp.operating_windows['PMP_01'][t]),'Continuous cooling policy mismatch')
        ready=inp.operating_windows['MILL_01'][t]
        require(states['RHF_01']==bool(ready and inp.equipment_availability['RHF_01'][t] and inp.operating_windows['RHF_01'][t]),'RHF readiness mismatch')
        require(states['CMP_01']==bool(inp.equipment_availability['CMP_01'][t] and inp.operating_windows['CMP_01'][t]),'Compressor policy mismatch')
        require(not states['MILL_01'] or states['RHF_01'] and states['CMP_01'],'Mill services unavailable')
        require(states['MILL_01']==(r>tol),'Mill run flag must match feed above numerical ledger tolerance')
        require(r<=min(c.mill_capacity_tph,c.rhf_capacity_tph)*dt*int(states['MILL_01'])+tol,'Rolling capacity/window violation')
        require(r<=inventory+tol,'Rolling borrowed unavailable billets')
        require(inventory+arrivals[t+1]<=c.inventory_max_t+tol,'Within-slot upper inventory bound violation')
        temperature=row['rhf_temperature_C']
        require(temperature==c.rhf_temperature_C if states['RHF_01'] else temperature is None,'Unqualified RHF temperature')
        aux=getattr(inp.background_load_forecast[t],'load_p50_kW' if inp.optimization_mode=='central' else 'load_p90_kW')
        actual={'IF_01':if_energy[t],'MILL_01':r*c.rolling_yield*c.mill_SEC_kWh_per_t_bar,
                'PMP_01':c.ratings_kW['PMP_01']*dt*int(states['PMP_01']),
                'RHF_01':c.ratings_kW['RHF_01']*dt*int(states['RHF_01']),
                'CMP_01':(c.compressor_loaded_kW if ready else c.compressor_idle_kW)*dt*int(states['CMP_01']), 'AUX':aux*dt}
        require(actual['MILL_01']<=c.ratings_kW['MILL_01']*dt+tol,'Mill energy above nameplate')
        powers={a:v/dt for a,v in actual.items()}
        reserve=dict(powers,IF_01=c.ratings_kW['IF_01']*int(on[t]),MILL_01=c.ratings_kW['MILL_01']*int(states['MILL_01']),CMP_01=c.ratings_kW['CMP_01']*int(states['CMP_01']))
        bound=sum(reserve[a]/c.power_factors[a] for a in reserve)
        average_kw=sum(powers.values()); reactive=sum(powers[a]*math.tan(math.acos(c.power_factors[a])) for a in powers)
        apparent=math.hypot(average_kw,reactive)
        require(bound<=c.demand_limit_kVA+tol and apparent<=c.demand_limit_kVA+tol,f'Demand violation {t}')
        if c.demand_limit_kVA-bound<=tol:binding.append(t)
        require(set(row['asset_kWh'])==set(actual),'Unknown/missing accounting assets')
        for a,value in actual.items():
            close(row['asset_kWh'][a],value,'Asset energy mismatch '+a);asset_totals[a]+=value
        slot=sum(actual.values());slot_cost=slot*inp.tariff_calendar[t].Rs_per_kWh
        close(row['tariff_Rs_per_kWh'],inp.tariff_calendar[t].Rs_per_kWh,'Tariff rate metadata mismatch')
        require(row['tariff_period']==inp.tariff_calendar[t].period,'Tariff period metadata mismatch')
        for key,v in dict(total_kWh=slot,total_kW=average_kw,kVA_bound=bound,average_kVA=apparent,tariff_cost_Rs=slot_cost).items(): close(row[key],v,'Load/cost mismatch '+key)
        close(row['billet_arrival_t'],arrivals[t+1],'Billet release mismatch')
        close(row['bar_t'],r*c.rolling_yield,'Rolling yield mismatch')
        total+=slot;cost+=slot_cost;bar+=r*c.rolling_yield
        inventory=inventory-r+arrivals[t+1];stock.append(inventory)
        require(c.inventory_min_t-tol<=inventory<=c.inventory_max_t+tol,'Inventory bounds')
        minstock=min(minstock,inventory);maxstock=max(maxstock,inventory)
        peak_bound=max(peak_bound,bound);peak_avg=max(peak_avg,apparent);peak_kw=max(peak_kw,sum(reserve.values()))
    for t,row in enumerate(result.inventory_trajectory):
        require(set(row)=={'boundary','timestamp','inventory_t'},'Unknown inventory fields')
        require(row['boundary']==t and timestamp(row['timestamp'])==origin+timedelta(minutes=t*c.slot_minutes),'Inventory boundary mismatch')
        close(row['inventory_t'],stock[t],'Inventory trajectory mismatch')
    billets=sum(arrivals);liquid=sum(h.liquid_t for h in inp.heats);sec=energy/liquid
    require(bar>=inp.production_order.bars_t-tol,'Production order not met')
    close(bar,inp.production_order.bars_t,'Unrequested bar overproduction')
    require(billets>=inp.production_order.billets_t-tol,'Billet requirement not met')
    require(inventory>=inp.production_order.final_inventory_min_t-tol,'Closing inventory reserve not met')
    if c.sec_target_kWh_per_t is not None:require(sec<=c.sec_target_kWh_per_t+tol,'SEC cap violated')
    metrics=dict(bars_t=bar,billets_t=billets,liquid_t=liquid,charge_t=liquid/c.melt_yield,
        predicted_total_kWh=total,predicted_IF_kWh=energy,predicted_IF_SEC_kWh_per_t=sec,
        predicted_peak_kVA_bound=peak_bound,predicted_peak_average_kVA=peak_avg,predicted_peak_kW_reserve=peak_kw,
        predicted_tariff_cost_Rs=cost,final_inventory_t=inventory,inventory_min_t=minstock,inventory_max_t=maxstock,
        furnace_utilization=occupied_minutes/(n*c.slot_minutes),reserved_furnace_utilization=reserved_minutes/(n*c.slot_minutes),
        rolling_utilization=sum(row['rolling_billet_t'] for row in result.load_trajectory)/(c.mill_capacity_tph*dt*n))
    require(set(result.predicted_metrics)==set(metrics)|{'asset_kWh','runtime_hours'},'Unexpected/missing metrics')
    for key,v in metrics.items():close(result.predicted_metrics[key],v,'Reported metric mismatch '+key)
    require(set(result.predicted_metrics['asset_kWh'])==set(asset_totals),'Reported asset list mismatch')
    require(set(result.predicted_metrics['runtime_hours'])==set(running),'Reported runtime list mismatch')
    for a,v in asset_totals.items():close(result.predicted_metrics['asset_kWh'][a],v,'Reported asset total mismatch '+a)
    for a,v in running.items():close(result.predicted_metrics['runtime_hours'][a],v*dt,'Reported runtime mismatch '+a)
    active=result.active_constraints
    require(active['binding_demand_slots']==binding,'Binding demand slots misreported')
    require(active['binding_inventory_lower']==[t for t,v in enumerate(stock) if v-c.inventory_min_t<=tol],'Binding lower stock misreported')
    require(active['binding_inventory_upper']==[t for t,v in enumerate(stock) if c.inventory_max_t-v<=tol],'Binding upper stock misreported')
    for key,v in dict(min_demand_slack_kVA=c.demand_limit_kVA-peak_bound,inventory_min_t=minstock,inventory_max_t=maxstock,
                     production_slack_t=bar-inp.production_order.bars_t,billet_slack_t=billets-inp.production_order.billets_t,
                     closing_inventory_slack_t=inventory-inp.production_order.final_inventory_min_t,
                     furnace_utilization=metrics['furnace_utilization'],reserved_furnace_utilization=metrics['reserved_furnace_utilization']).items():
        close(active[key],v,'Binding/slack metric mismatch '+key)
    require(active['sec_target_kWh_per_t']==c.sec_target_kWh_per_t,'SEC target metadata altered')
    if c.sec_target_kWh_per_t is None:require(active['SEC_slack'] is None,'Invented SEC cap slack')
    else:close(active['SEC_slack'],c.sec_target_kWh_per_t-sec,'SEC slack misreported')
    objective=cost if inp.objective_mode=='cost' else total if inp.objective_mode=='energy' else 0.0
    close(result.solver_status['best_feasible_objective'],objective,'Solver objective does not match independent accounting')
    return dict(feasible=not errors,violations=errors,independent_metrics=metrics,
                mass_residual_t=inp.initial_inventory_t+billets-bar/c.rolling_yield-inventory,
                energy_residual_kWh=total-sum(asset_totals.values()),binding_demand_slots=binding,
                checked_slots=n,checked_heats=len(result.schedule))
