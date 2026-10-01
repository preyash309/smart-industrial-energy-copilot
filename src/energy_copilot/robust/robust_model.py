"""Successor constraints added to the frozen MILP; shared decisions across scenarios."""
from dataclasses import dataclass, asdict, replace
from datetime import datetime
import math
import importlib.metadata
from energy_copilot.common import load_config,values
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from energy_copilot.optimization.model import build_model
from energy_copilot.optimization.objective import set_objective
from energy_copilot.optimization.solve import extract_result
from energy_copilot.optimization.contracts import OptimizerResult
from .contracts import ReservePolicy
from .scenarios import scenario_coefficients
from .checker import check_robust


def reduce_scenario_candidates(inp,policy,scenarios,practices):
    """Safe necessary start bounds from minimum scenario occupancy per heat.

    This reduces a one-minute grid without altering any feasible decisions. The
    minima range over ALL candidate contexts; no outcomes or solver are consulted.
    """
    c=inp.constraints;origin=datetime.fromisoformat(inp.forecast_origin);groups=[];gaps=[];last_durations=[]
    for pos,h in enumerate(inp.heats):
        ks=[k for k in inp.heat_candidates if k.heat_id==h.heat_id and k.prediction.practice_mode in practices]
        if not ks:return None
        lengths=[];durations=[]
        for k in ks:
            q=50 if inp.optimization_mode=='central' else 90
            d=getattr(k.prediction,f'duration_p{q}_min')
            ds=[scenario_coefficients(k,inp,s,pos)[1] for s in scenarios];maximum=max([d,*ds])
            lengths.append(math.ceil((math.ceil((maximum-c.tolerance)/c.candidate_step_minutes)*c.candidate_step_minutes+policy.buffer(k.prediction)-c.tolerance)/c.candidate_step_minutes)*c.candidate_step_minutes)
            durations.append(maximum)
        groups.append(ks);gaps.append(min(lengths));last_durations.append(min(durations))
    total=c.horizon_slots*15-policy.end_margin_min
    if sum(gaps[:-1])+last_durations[-1]>total+c.tolerance:return None
    kept=[];before=0
    for i,ks in enumerate(groups):
        after=sum(gaps[i:-1])+last_durations[-1]
        subset=[k for k in ks if before-c.tolerance<=(datetime.fromisoformat(k.start)-origin).total_seconds()/60<=total-after+c.tolerance]
        if not subset:return None
        kept.extend(subset);before+=gaps[i]
    return replace(inp,heat_candidates=tuple(kept))


@dataclass(frozen=True)
class RobustPlan:
    plan: OptimizerResult
    policy: ReservePolicy
    scenarios: tuple
    checker: dict

    def to_dict(self):return asdict(self)


def build_robust_model(inp,policy,scenarios,practices):
    policy.validate();reduced=reduce_scenario_candidates(inp,policy,scenarios,practices)
    if reduced is None:return None,{},'No eligible candidates under required scenario reserve/buffer occupancy bounds'
    m,co,reason=build_model(reduced,practices)
    if m is None:return m,co,reason
    c=inp.constraints;n=c.horizon_slots;origin=datetime.fromisoformat(inp.forecast_origin)
    for t,v in enumerate(getattr(inp,'known_arrivals',())):
        if v:m.arrivals[t].set_value(m.arrivals[t].expr+v)
    if getattr(inp,'committed_first_feed_t',None) is not None:m.rolling_t[0].fix(inp.committed_first_feed_t)
    by={h.heat_id:[k for k,v in co.items() if v['candidate'].heat_id==h.heat_id] for h in inp.heats}
    m.robust_constraints=pyo.ConstraintList()
    for h in inp.heats:
        m.robust_constraints.add(sum(co[k]['end']*m.x[k] for k in by[h.heat_id])<=n*15-policy.end_margin_min)
    for a,b in zip(inp.heats,inp.heats[1:]):
        m.robust_constraints.add(sum((co[k]['reserved_end']+policy.buffer(co[k]['candidate'].prediction))*m.x[k] for k in by[a.heat_id])<=sum(co[k]['start']*m.x[k] for k in by[b.heat_id]))
    m.S=pyo.RangeSet(0,len(scenarios)-1) if scenarios else pyo.Set(initialize=[])
    m.scenario_inventory=pyo.Var(m.S,m.B,bounds=(c.inventory_min_t,c.inventory_max_t))
    for si,s in enumerate(scenarios):
        durations={};ends={};releases={t:[] for t in range(n+1)};powered={t:[] for t in range(n)}
        for pos,h in enumerate(inp.heats):
            for k in by[h.heat_id]:
                v=co[k];e,d=scenario_coefficients(v['candidate'],inp,s,pos);end=v['start']+d
                durations[k]=d;ends[k]=end
                occupied=range(int(v['start']//15),math.ceil((end-c.tolerance)/15))
                if end>n*15-policy.end_margin_min+c.tolerance or any(t>=n or not(inp.equipment_availability['IF_01'][t] and inp.operating_windows['IF_01'][t]) for t in occupied):
                    m.x[k].fix(0);continue
                releases[math.ceil((end-c.tolerance)/15)].append(k)
                powerstart=end-e/c.ratings_kW['IF_01']*60
                for t in occupied:
                    if min(end,(t+1)*15)>max(powerstart,t*15)+c.tolerance:powered[t].append(k)
        for a,b in zip(inp.heats,inp.heats[1:]):
            m.robust_constraints.add(sum((math.ceil((ends[k]-c.tolerance)/c.candidate_step_minutes)*c.candidate_step_minutes+policy.buffer(co[k]['candidate'].prediction))*m.x[k] for k in by[a.heat_id])<=sum(co[k]['start']*m.x[k] for k in by[b.heat_id]))
        m.robust_constraints.add(m.scenario_inventory[si,0]==inp.initial_inventory_t)
        liquid={h.heat_id:h.liquid_t for h in inp.heats}
        for t in range(n):
            arrivals=sum(liquid[co[k]['candidate'].heat_id]*c.cast_yield*m.x[k] for k in releases[t+1])+ (inp.known_arrivals[t+1] if getattr(inp,'known_arrivals',()) else 0.0)
            m.robust_constraints.add(m.rolling_t[t]<=m.scenario_inventory[si,t])
            m.robust_constraints.add(m.scenario_inventory[si,t+1]==m.scenario_inventory[si,t]-m.rolling_t[t]+arrivals)
            m.robust_constraints.add(m.scenario_inventory[si,t]+arrivals<=c.inventory_max_t)
            on=sum(m.x[k] for k in powered[t])
            if powered[t]:m.robust_constraints.add(on<=1)
            m.robust_constraints.add(on<=m.pump_on[t])
            aux=getattr(inp.background_load_forecast[t],f'load_p{90 if s.use_upper_quantiles or inp.optimization_mode=="conservative" else 50}_kW')
            bound=(c.ratings_kW['IF_01']/c.power_factors['IF_01']*on+c.ratings_kW['MILL_01']/c.power_factors['MILL_01']*m.asset_run['MILL_01',t]+
                   c.ratings_kW['CMP_01']/c.power_factors['CMP_01']*m.asset_run['CMP_01',t]+sum(m.asset_energy[a,t]/.25/c.power_factors[a] for a in ('RHF_01','PMP_01'))+aux/c.power_factors['AUX'])
            m.robust_constraints.add(bound<=c.demand_limit_kVA)
        m.robust_constraints.add(m.scenario_inventory[si,n]>=inp.production_order.final_inventory_min_t)
    return m,co,None


def optimize_robust(inp,policy=ReservePolicy(),scenarios=(),practices=('practice_loss_40',)):
    inp.validate();m,co,reason=build_robust_model(inp,policy,scenarios,practices)
    if m is None:
        return RobustPlan(OptimizerResult('infeasible',False,inp.optimization_mode,inp.objective_mode,reason=reason,forecast_origin=inp.forecast_origin),policy,scenarios,{})
    options=inp.constraints.solver_options;solver=Highs();solver.config.load_solution=False
    for package,key in [('pyomo','pyomo_version'),('highspy','highspy_version')]:
        if importlib.metadata.version(package)!=options[key]:raise RuntimeError('Unqualified solver runtime')
    solver.config.time_limit=options['time_limit_seconds'];solver.highs_options=dict(threads=1,random_seed=options['seed'],parallel='off',mip_rel_gap=0,mip_abs_gap=options['absolute_gap'])
    node_limit=values(load_config('configs/robustness_v1.yaml'))['solver_node_limit']
    solver.highs_options['mip_max_nodes']=node_limit
    # Feasibility is a separate gate; objective never buys violations/slack.
    stages=[]
    for objective in ('feasibility',inp.objective_mode) if inp.objective_mode!='feasibility' else ('feasibility',):
        if objective!='feasibility':set_objective(m,inp)
        solver.config.warmstart=objective!='feasibility'
        try:answer=solver.solve(m)
        except (MemoryError,RuntimeError) as exc:
            p=OptimizerResult('solver_error',False,inp.optimization_mode,inp.objective_mode,reason=f'Solver failed explicitly: {type(exc).__name__}: {exc}',forecast_origin=inp.forecast_origin)
            return RobustPlan(p,policy,scenarios,{'feasible':False,'violations':[p.reason]})
        term=answer.termination_condition.name
        feasible=answer.best_feasible_objective is not None and math.isfinite(answer.best_feasible_objective)
        stages.append(dict(stage=objective,termination=term,feasible=feasible))
        if not feasible:
            p=OptimizerResult('infeasible' if term=='infeasible' else 'solver_limit',False,inp.optimization_mode,inp.objective_mode,reason='No feasible robust continuation; reserve/scenarios remain hard',solver_status={'stages':stages},forecast_origin=inp.forecast_origin)
            return RobustPlan(p,policy,scenarios,{'feasible':False,'violations':[p.reason]})
        answer.solution_loader.load_vars()
    for t in m.T:
        if abs(pyo.value(m.rolling_t[t]))<=inp.constraints.tolerance:m.asset_run['MILL_01',t].set_value(0)
    status=dict(termination=term,best_feasible_objective=float(answer.best_feasible_objective),best_objective_bound=float(answer.best_objective_bound),stages=stages,
                library='Pyomo/HiGHS frozen Phase-II-C runtime',threads=1,seed=options['seed'],node_limit=node_limit)
    result=extract_result(inp,m,co,'optimal' if term=='optimal' else 'feasible',status)
    result=replace(result,assumptions=result.assumptions+('Successor remaining-horizon accounting geometry may start before decision_time in the current quarter-hour; posted arrivals and already issued rolling feed are constants. Completed heat electricity is excluded from the remaining-work objective; only full twin replay reports full-day energy.',))
    checked=check_robust(inp,result,policy,scenarios)
    result=replace(result,releasable=checked['feasible'],checker=checked,status=result.status if checked['feasible'] else 'checker_failed',reason=None if checked['feasible'] else '; '.join(checked['violations']))
    return RobustPlan(result,policy,scenarios,checked)
