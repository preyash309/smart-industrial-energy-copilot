"""C1 feasibility MILP. Contains no training, tables, or simulator calls."""
import pyomo.environ as pyo
from .candidates import coefficients
from .contracts import ASSETS


def build_model(inp,practices=None,fixed_schedule=None,fixed_rolling=None):
    inp.validate(); c=inp.constraints;co,by_heat=coefficients(inp,practices)
    if any(not ks for ks in by_heat.values()): return None,co,'No eligible in-horizon candidates under duration, availability and ordered occupancy constraints'
    n=c.horizon_slots;dt=c.slot_minutes/60
    m=pyo.ConcreteModel();m.K=pyo.Set(initialize=list(co));m.T=pyo.RangeSet(0,n-1);m.B=pyo.RangeSet(0,n)
    m.A=pyo.Set(initialize=ASSETS);m.x=pyo.Var(m.K,domain=pyo.Binary)
    m.inventory=pyo.Var(m.B,bounds=(c.inventory_min_t,c.inventory_max_t))
    m.rolling_t=pyo.Var(m.T,domain=pyo.NonNegativeReals)
    m.asset_run=pyo.Var(m.A,m.T,domain=pyo.Binary)
    m.furnace_on=pyo.Var(m.T,domain=pyo.Binary);m.pump_on=pyo.Var(m.T,domain=pyo.Binary)
    m.constraints=pyo.ConstraintList()
    for h in inp.heats: m.constraints.add(sum(m.x[k] for k in by_heat[h.heat_id])==1)
    for left,right in zip(inp.heats,inp.heats[1:]):
        m.constraints.add(sum(co[k]['reserved_end']*m.x[k] for k in by_heat[left.heat_id])<=sum(co[k]['start']*m.x[k] for k in by_heat[right.heat_id]))
    micro={u:[] for u in range(n*c.slot_minutes//c.candidate_step_minutes)}
    powered={t:[] for t in range(n)};release={t:[] for t in range(1,n+1)}
    for k,v in co.items():
        for u in v['micro_slots']:micro[u].append(k)
        for t in v['power_slots']:powered[t].append(k)
        release[v['release_boundary']].append(k)
    for ks in micro.values():
        if ks:m.constraints.add(sum(m.x[k] for k in ks)<=1)
    liquid={h.heat_id:h.liquid_t for h in inp.heats}
    m.arrivals=pyo.Expression(m.B,rule=lambda _,t: 0 if t==0 else sum(liquid[co[k]['candidate'].heat_id]*c.cast_yield*m.x[k] for k in release[t]))
    m.constraints.add(m.inventory[0]==inp.initial_inventory_t)
    m.constraints.add(m.inventory[n]>=inp.production_order.final_inventory_min_t)
    m.constraints.add(sum(m.arrivals[t] for t in range(1,n+1))>=inp.production_order.billets_t)
    m.constraints.add(sum(m.rolling_t[t]*c.rolling_yield for t in m.T)>=inp.production_order.bars_t)
    # Do not overproduce gratuitously; exact ordered bar output conserves stock.
    m.constraints.add(sum(m.rolling_t[t]*c.rolling_yield for t in m.T)==inp.production_order.bars_t)
    for t in m.T:
        for k in powered[t]:m.constraints.add(m.furnace_on[t]>=m.x[k])
        m.constraints.add(m.furnace_on[t]<=sum(m.x[k] for k in powered[t]))
        m.constraints.add(m.asset_run['IF_01',t]==m.furnace_on[t])
        m.constraints.add(m.pump_on[t]==m.asset_run['PMP_01',t])
        m.constraints.add(m.pump_on[t]>=m.furnace_on[t])
        m.constraints.add(m.pump_on[t]==int(inp.equipment_availability['PMP_01'][t] and inp.operating_windows['PMP_01'][t]))
        for a in ASSETS:
            m.constraints.add(m.asset_run[a,t]<=int(inp.equipment_availability[a][t] and inp.operating_windows[a][t]))
        ready=bool(inp.operating_windows['MILL_01'][t])
        m.constraints.add(m.asset_run['RHF_01',t]==int(ready and inp.equipment_availability['RHF_01'][t] and inp.operating_windows['RHF_01'][t]))
        m.constraints.add(m.asset_run['CMP_01',t]==int(inp.equipment_availability['CMP_01'][t] and inp.operating_windows['CMP_01'][t]))
        m.constraints.add(m.asset_run['MILL_01',t]<=m.asset_run['RHF_01',t])
        m.constraints.add(m.asset_run['MILL_01',t]<=m.asset_run['CMP_01',t])
        m.constraints.add(m.rolling_t[t]<=min(c.mill_capacity_tph,c.rhf_capacity_tph)*dt*m.asset_run['MILL_01',t])
        m.constraints.add(m.rolling_t[t]*c.rolling_yield*c.mill_SEC_kWh_per_t_bar<=c.ratings_kW['MILL_01']*dt*m.asset_run['MILL_01',t])
        m.constraints.add(m.rolling_t[t]<=m.inventory[t])
        m.constraints.add(m.inventory[t+1]==m.inventory[t]-m.rolling_t[t]+m.arrivals[t+1])
        # Upper-bound stock even if all same-slot billets arrive before consumption.
        m.constraints.add(m.inventory[t]+m.arrivals[t+1]<=c.inventory_max_t)
    q='50' if inp.optimization_mode=='central' else '90'
    def energy(_,a,t):
        if a=='IF_01':return sum(v['slot_energy'].get(t,0)*m.x[k] for k,v in co.items() if t in v['slot_energy'])
        if a=='MILL_01':return m.rolling_t[t]*c.rolling_yield*c.mill_SEC_kWh_per_t_bar
        if a=='PMP_01':return c.ratings_kW[a]*dt*m.pump_on[t]
        if a=='RHF_01':return c.ratings_kW[a]*dt*m.asset_run[a,t]
        if a=='CMP_01':return (c.compressor_loaded_kW if inp.operating_windows['MILL_01'][t] else c.compressor_idle_kW)*dt*m.asset_run[a,t]
    m.asset_energy=pyo.Expression(m.A,m.T,rule=energy)
    m.background_kW=pyo.Param(m.T,initialize={t:getattr(inp.background_load_forecast[t],f'load_p{q}_kW') for t in range(n)})
    m.total_energy=pyo.Expression(m.T,rule=lambda _,t:sum(m.asset_energy[a,t] for a in m.A)+m.background_kW[t]*dt)
    def reserve(_,t):
        return (c.ratings_kW['IF_01']/c.power_factors['IF_01']*m.furnace_on[t]+c.ratings_kW['MILL_01']/c.power_factors['MILL_01']*m.asset_run['MILL_01',t]
                +c.ratings_kW['CMP_01']/c.power_factors['CMP_01']*m.asset_run['CMP_01',t]
                +sum(m.asset_energy[a,t]/dt/c.power_factors[a] for a in ('RHF_01','PMP_01'))+m.background_kW[t]/c.power_factors['AUX'])
    m.kVA_bound=pyo.Expression(m.T,rule=reserve)
    m.demand=pyo.Constraint(m.T,rule=lambda _,t:m.kVA_bound[t]<=c.demand_limit_kVA)
    if c.sec_target_kWh_per_t is not None:
        m.sec=pyo.Constraint(expr=sum(v['energy']*m.x[k] for k,v in co.items())<=c.sec_target_kWh_per_t*sum(h.liquid_t for h in inp.heats))
    if fixed_schedule is not None:
        for k in m.K:m.x[k].fix(int(k in fixed_schedule))
    if fixed_rolling is not None:
        for t in m.T:m.rolling_t[t].fix(fixed_rolling[t])
    # C1 only; C2/C3 objectives are added after the feasibility gate passes.
    m.objective=pyo.Objective(expr=0,sense=pyo.minimize)
    return m,co,None
