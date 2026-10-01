"""Necessary-condition diagnostics, independent of solver status certification."""
def infeasibility_diagnostics(inp,practices=None):
    c=inp.constraints;proof=[];dt=c.slot_minutes/60
    eligible=[t for t in range(c.horizon_slots) if all(inp.equipment_availability[a][t] and inp.operating_windows[a][t] for a in ('MILL_01','RHF_01','CMP_01'))]
    bars_max=len(eligible)*dt*min(c.mill_capacity_tph,c.rhf_capacity_tph,c.ratings_kW['MILL_01']/(c.rolling_yield*c.mill_SEC_kWh_per_t_bar))*c.rolling_yield
    billets=sum(h.liquid_t*c.cast_yield for h in inp.heats)
    if inp.production_order.bars_t>bars_max+c.tolerance:proof.append(f'Order {inp.production_order.bars_t:g} t bars exceeds available rolling/RHF capacity {bars_max:g} t')
    if inp.production_order.billets_t>billets+c.tolerance:proof.append(f'Billet requirement exceeds fixed-heat yield: {inp.production_order.billets_t:g} > {billets:g} t')
    final=inp.initial_inventory_t+billets-inp.production_order.bars_t/c.rolling_yield
    if final<inp.production_order.final_inventory_min_t-c.tolerance:proof.append(f'Closing mass ledger {final:g} t cannot meet reserve {inp.production_order.final_inventory_min_t:g} t')
    if c.sec_target_kWh_per_t is not None:
        allowed=set(practices or c.supported_practices);q='50' if inp.optimization_mode=='central' else '90'
        minimum=sum(min(getattr(k.prediction,f'energy_p{q}_kWh') for k in inp.heat_candidates if k.heat_id==h.heat_id and k.prediction.practice_mode in allowed) for h in inp.heats)
        lower=minimum/sum(h.liquid_t for h in inp.heats)
        if lower>c.sec_target_kWh_per_t+c.tolerance:proof.append(f'Even unconstrained candidate SEC lower bound {lower:.6g} exceeds explicit cap {c.sec_target_kWh_per_t:g} kWh/t liquid')
    return tuple(proof)
