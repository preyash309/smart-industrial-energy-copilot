"""Feasibility solve/release gate. The API returns no Pyomo objects."""
from dataclasses import replace, asdict
from datetime import timedelta
import math
import importlib.metadata
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from .model import build_model
from .checker import check_schedule
from .contracts import ASSETS, OptimizerResult, timestamp
from .constraints import infeasibility_diagnostics


ASSUMPTIONS=(
    'OPTIMIZER-PREDICTED only; matched-condition twin replay has not been performed.',
    '96 quarter-hour accounting slots; candidate starts use the explicit configurable subslot grid.',
    'Fixed ordered 10-t heats. Candidate E/D come only from frozen PredictionService; p90 is not a physical guarantee.',
    'Heat energy is a rated-power tail; preceding cycle time is nonpowered. Full nameplate IF/mill/compressor demand reserves protect subslot peaks in this reduced representation.',
    'Additive feeder kVA is a conservative triangle-inequality bound. Average combined P/Q apparent power is reported separately.',
    'Billets post at the next accounting boundary; rolling may use opening stock only. Upper inventory reserve assumes all arrivals before consumption.',
    'Pump circulates continuously when available; RHF/compressor retain configured readiness/idle calendar duties.',
    'RHF uses only the configured in-range setpoint, not an independently solved thermal trajectory. Metallurgy/chemistry is not solved.',
    'Only normal and explicitly synthetic practice_loss_40 are supported; the intervention is not field-qualified.',
    'Health probabilities are informational; availability restrictions must be supplied externally.',
    'No SEC cap is inferred. Input cap, if present, is enforced against the selected quantile.',
    'Tariff cost covers electricity energy only, without demand charges, kVAh billing, fuel, FPPAS, emissions or savings claims.'
)


def optimize(inp,mode=None,objective=None,practices=None,fixed_schedule=None,fixed_rolling=None):
    if mode is not None:inp=replace(inp,optimization_mode=mode)
    if objective is not None:inp=replace(inp,objective_mode=objective)
    inp.validate();m,co,reason=build_model(inp,practices,fixed_schedule,fixed_rolling)
    if m is None:return OptimizerResult('infeasible',False,inp.optimization_mode,inp.objective_mode,reason=reason,assumptions=ASSUMPTIONS,forecast_origin=inp.forecast_origin)
    if inp.objective_mode!='feasibility':
        from .objective import set_objective
        set_objective(m,inp)
    solver=Highs();options=inp.constraints.solver_options
    for package,key in [('pyomo','pyomo_version'),('highspy','highspy_version')]:
        if importlib.metadata.version(package)!=options[key]:raise RuntimeError('Unqualified solver runtime; install pinned Phase-II-C lock')
    solver.config.load_solution=False;solver.config.time_limit=options['time_limit_seconds']
    solver.highs_options=dict(threads=options['threads'],random_seed=options['seed'],parallel='off',
                             mip_rel_gap=options['relative_gap'],mip_abs_gap=options['absolute_gap'])
    answer=solver.solve(m);termination=answer.termination_condition.name
    finite=answer.best_feasible_objective is not None and math.isfinite(answer.best_feasible_objective)
    status=dict(termination=termination,best_feasible_objective=float(answer.best_feasible_objective) if finite else None,
                best_objective_bound=float(answer.best_objective_bound) if answer.best_objective_bound is not None and math.isfinite(answer.best_objective_bound) else None,
                library=f"Pyomo {options['pyomo_version']} / HiGHS {options['highspy_version']}",threads=options['threads'],seed=options['seed'])
    if not finite:
        diagnoses=infeasibility_diagnostics(inp,practices)
        return OptimizerResult('infeasible' if termination=='infeasible' else 'solver_limit',False,inp.optimization_mode,inp.objective_mode,
                               solver_status=status,reason='; '.join(diagnoses) if diagnoses else 'No feasible incumbent; inspect production, windows, stock, duration, demand and SEC constraints',assumptions=ASSUMPTIONS,forecast_origin=inp.forecast_origin)
    answer.solution_loader.load_vars()
    # The MILP's run indicator has no idle-drive cost. Numerically zero feed
    # leaves a free binary: canonicalize it OFF using the ledger tolerance,
    # without altering feed, inventory, energy or the objective.
    for t in m.T:
        if abs(pyo.value(m.rolling_t[t]))<=inp.constraints.tolerance:m.asset_run['MILL_01',t].set_value(0)
    result=extract_result(inp,m,co,'optimal' if termination=='optimal' else 'feasible',status)
    checked=check_schedule(inp,result)
    validated=replace(result,releasable=checked['feasible'],status=result.status if checked['feasible'] else 'checker_failed',checker=checked,
                      reason=None if checked['feasible'] else '; '.join(checked['violations']))
    from .explain import explanation_data
    return replace(validated,explanation_data=explanation_data(inp,validated))


def extract_result(inp,m,co,status,solver_status):
    c=inp.constraints;origin=timestamp(inp.forecast_origin);dt=c.slot_minutes/60; val=pyo.value
    schedule=[]
    for k,v in co.items():
        if val(m.x[k])<.5:continue
        p=v['candidate'].prediction
        schedule.append(dict(candidate_id=k,heat_id=p.heat_id,start=v['candidate'].start,selected_practice=p.practice_mode,
            predicted_end=(origin+timedelta(minutes=v['end'])).isoformat(),reserved_end=(origin+timedelta(minutes=v['reserved_end'])).isoformat(),
            energy_p50_kWh=p.energy_p50_kWh,energy_p90_kWh=p.energy_p90_kWh,duration_p50_min=p.duration_p50_min,duration_p90_min=p.duration_p90_min,
            selected_energy_kWh=v['energy'],selected_duration_min=v['duration']))
    schedule.sort(key=lambda row:row['start'])
    trajectory=[];totals={a:0.0 for a in ASSETS+('AUX',)};runtime={a:0.0 for a in ASSETS}
    for t in m.T:
        states={a:bool(val(m.asset_run[a,t])>.5) for a in ASSETS}
        energy={a:float(val(m.asset_energy[a,t])) for a in ASSETS};energy['AUX']=float(val(m.background_kW[t])*dt)
        for a,v in energy.items():totals[a]+=v
        for a,b in states.items():runtime[a]+=dt*int(b)
        kw=sum(energy.values())/dt;q=sum(v/dt*math.tan(math.acos(c.power_factors[a])) for a,v in energy.items())
        trajectory.append(dict(slot=int(t),interval_start=(origin+timedelta(minutes=int(t)*c.slot_minutes)).isoformat(),
            interval_end=(origin+timedelta(minutes=(int(t)+1)*c.slot_minutes)).isoformat(),
            asset_run=states,furnace_on=bool(val(m.furnace_on[t])>.5),pump_on=bool(val(m.pump_on[t])>.5),
            asset_kWh=energy,total_kWh=float(val(m.total_energy[t])),total_kW=kw,average_kVA=math.hypot(kw,q),
            kVA_bound=float(val(m.kVA_bound[t])),rolling_billet_t=float(val(m.rolling_t[t])),bar_t=float(val(m.rolling_t[t])*c.rolling_yield),
            billet_arrival_t=float(val(m.arrivals[t+1])),rhf_temperature_C=c.rhf_temperature_C if states['RHF_01'] else None,
            tariff_Rs_per_kWh=inp.tariff_calendar[t].Rs_per_kWh,tariff_period=inp.tariff_calendar[t].period,
            tariff_cost_Rs=float(val(m.total_energy[t])*inp.tariff_calendar[t].Rs_per_kWh)))
    inv=tuple(dict(boundary=int(t),timestamp=(origin+timedelta(minutes=int(t)*c.slot_minutes)).isoformat(),inventory_t=float(val(m.inventory[t]))) for t in m.B)
    liquid=sum(h.liquid_t for h in inp.heats);minutes=c.horizon_slots*c.slot_minutes
    metrics=dict(bars_t=sum(r['bar_t'] for r in trajectory),billets_t=sum(r['billet_arrival_t'] for r in trajectory),liquid_t=liquid,charge_t=liquid/c.melt_yield,
        predicted_total_kWh=sum(r['total_kWh'] for r in trajectory),predicted_IF_kWh=totals['IF_01'],predicted_IF_SEC_kWh_per_t=totals['IF_01']/liquid,
        predicted_peak_kVA_bound=max(r['kVA_bound'] for r in trajectory),predicted_peak_average_kVA=max(r['average_kVA'] for r in trajectory),
        predicted_peak_kW_reserve=max(c.ratings_kW['IF_01']*int(r['furnace_on'])+c.ratings_kW['MILL_01']*int(r['asset_run']['MILL_01'])+
            c.ratings_kW['CMP_01']*int(r['asset_run']['CMP_01'])+sum(r['asset_kWh'][a]/dt for a in ('RHF_01','PMP_01','AUX')) for r in trajectory),
        predicted_tariff_cost_Rs=sum(r['tariff_cost_Rs'] for r in trajectory),final_inventory_t=inv[-1]['inventory_t'],
        inventory_min_t=min(r['inventory_t'] for r in inv),inventory_max_t=max(r['inventory_t'] for r in inv),
        furnace_utilization=sum(r['selected_duration_min'] for r in schedule)/minutes,
        reserved_furnace_utilization=sum((timestamp(r['reserved_end'])-timestamp(r['start'])).total_seconds()/60 for r in schedule)/minutes,
        rolling_utilization=sum(r['rolling_billet_t'] for r in trajectory)/(c.mill_capacity_tph*dt*c.horizon_slots),asset_kWh=totals,runtime_hours=runtime)
    active=dict(binding_demand_slots=[r['slot'] for r in trajectory if c.demand_limit_kVA-r['kVA_bound']<=c.tolerance],
        min_demand_slack_kVA=c.demand_limit_kVA-metrics['predicted_peak_kVA_bound'],inventory_min_t=metrics['inventory_min_t'],inventory_max_t=metrics['inventory_max_t'],
        binding_inventory_lower=[r['boundary'] for r in inv if r['inventory_t']-c.inventory_min_t<=c.tolerance],
        binding_inventory_upper=[r['boundary'] for r in inv if c.inventory_max_t-r['inventory_t']<=c.tolerance],
        production_slack_t=metrics['bars_t']-inp.production_order.bars_t,billet_slack_t=metrics['billets_t']-inp.production_order.billets_t,
        closing_inventory_slack_t=metrics['final_inventory_t']-inp.production_order.final_inventory_min_t,
        sec_target_kWh_per_t=c.sec_target_kWh_per_t,SEC_slack=None if c.sec_target_kWh_per_t is None else c.sec_target_kWh_per_t-metrics['predicted_IF_SEC_kWh_per_t'],
        furnace_utilization=metrics['furnace_utilization'],reserved_furnace_utilization=metrics['reserved_furnace_utilization'],
        binary_start_variables=len(co),constraints=sum(1 for _ in m.component_data_objects(pyo.Constraint,active=True)))
    return OptimizerResult(status,False,inp.optimization_mode,inp.objective_mode,tuple(schedule),metrics,inv,tuple(trajectory),active,
        tuple(asdict(p) for p in inp.health_predictions),ASSUMPTIONS,(),solver_status,forecast_origin=inp.forecast_origin)
