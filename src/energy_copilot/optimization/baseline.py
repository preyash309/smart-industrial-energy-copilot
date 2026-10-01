"""Tariff-blind reference plan, using predicted cycles and configured rolling duty."""
from dataclasses import replace
from .candidates import coefficients
from .solve import optimize
from .contracts import OptimizerResult


def baseline_schedule(inp):
    """Same orders/stock/tariff/uncertainty as optimized plan; normal practice only.

    Back-to-back earliest starts on the declared start grid. Predicted duration
    replaces the physical simulator's unknown future duration; this is a predicted
    reference schedule, NOT a realized Phase-I schedule or replay.
    """
    inp.validate();co,by_heat=coefficients(inp,('normal',));last=0;chosen=[]
    arrivals=[0.0]*(inp.constraints.horizon_slots+1);c=inp.constraints
    for h in inp.heats:
        feasible=[k for k in by_heat[h.heat_id] if co[k]['start']>=last-c.tolerance]
        if not feasible:return OptimizerResult('infeasible',False,inp.optimization_mode,inp.objective_mode,reason='Reference earliest-start policy has no feasible candidate')
        k=min(feasible,key=lambda k:(co[k]['start'],k));chosen.append(k);last=co[k]['reserved_end']
        arrivals[co[k]['release_boundary']]+=h.liquid_t*c.cast_yield
    rolling=[];inventory=inp.initial_inventory_t;remaining=inp.production_order.bars_t/c.rolling_yield
    for t in range(c.horizon_slots):
        allowed=all(inp.equipment_availability[a][t] and inp.operating_windows[a][t] for a in ('MILL_01','RHF_01','CMP_01'))
        amount=max(0,min(c.mill_capacity_tph*c.slot_minutes/60,c.rhf_capacity_tph*c.slot_minutes/60,inventory,remaining)) if allowed else 0
        rolling.append(amount);remaining-=amount;inventory+=arrivals[t+1]-amount
    if remaining>c.tolerance:return OptimizerResult('infeasible',False,inp.optimization_mode,inp.objective_mode,reason='Reference rolling policy cannot fulfill order')
    return optimize(inp,practices=('normal',),fixed_schedule=set(chosen),fixed_rolling=rolling)
