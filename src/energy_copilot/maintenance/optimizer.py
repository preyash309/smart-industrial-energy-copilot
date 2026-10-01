"""Robust shared-decision MILP with optional, movable service windows."""
from dataclasses import dataclass,asdict,replace
from datetime import datetime
import importlib.metadata,math
import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from pyomo.core.expr.visitor import identify_variables
from energy_copilot.common import load_config,values
from energy_copilot.optimization.objective import set_objective
from energy_copilot.optimization.solve import extract_result
from energy_copilot.optimization.contracts import OptimizerResult
from energy_copilot.robust.robust_model import build_robust_model,optimize_robust
from energy_copilot.robust.scenarios import scenario_coefficients
from energy_copilot.robust.checker import check_robust
from .contracts import MaintenanceAction,settings


@dataclass(frozen=True)
class MaintenancePlan:
    plan: OptimizerResult
    actions: tuple
    candidates: tuple
    policy: dict
    checker: dict
    stages: tuple

    def to_dict(self):return asdict(self)


def candidates(inp,eligible,maintenance_config=None):
    cfg=maintenance_config or settings();decision=pd.Timestamp(inp.decision_time);day=pd.Timestamp(inp.template.forecast_origin)
    windows=[]
    for asset in ('MILL_01','PMP_01'):
        if not eligible.get(asset,False):continue
        rule=cfg['service'][asset]
        for hour in rule['candidate_start_hour']:
            at=day+pd.Timedelta(hours=hour);end=at+pd.Timedelta(minutes=rule['duration_min']+rule['restart_delay_min'])
            if at<decision or end>day+pd.Timedelta(days=1):continue
            lo=int((at-pd.Timestamp(inp.forecast_origin)).total_seconds()/900)
            hi=int((end-pd.Timestamp(inp.forecast_origin)).total_seconds()/900)
            if lo<0 or hi>inp.constraints.horizon_slots:continue
            if any(not(inp.equipment_availability[asset][t] and inp.operating_windows[asset][t]) for t in range(lo,hi)):continue
            action=MaintenanceAction(asset,at.isoformat(),rule['duration_min'],rule['intervention_type'],rule['condition_effect'],rule['direct_cost_Rs'])
            action.validate(cfg,values(load_config(cfg['plant_config']))['start'],values(load_config('configs/robustness_v1.yaml'))['horizon_days'])
            windows.append(action)
    return tuple(windows)


def _deactivate_constant_pump_equation(model,t):
    found=[]
    for key in model.constraints:
        row=model.constraints[key]
        if not row.active or not row.equality:continue
        identified=list(identify_variables(row.body))
        if len(identified)==1 and identified[0] is model.pump_on[t] and row.lower is not None and row.upper is not None:
            found.append(row)
    if len(found)!=1:raise RuntimeError('Frozen pump-equality structure changed; refuse maintenance optimization')
    found[0].deactivate()


def _checked_input(inp,actions):
    # Recompute external availability from action controls for the independent
    # frozen checker. The MILP itself never receives this adjusted checker input.
    original={a:list(v) for a,v in inp.template.equipment_availability.items()}
    day=pd.Timestamp(inp.template.forecast_origin);offset=int((pd.Timestamp(inp.forecast_origin)-day).total_seconds()/900)
    for action in actions:
        lo=int((pd.Timestamp(action.start_time)-day).total_seconds()/900);hi=lo+action.duration_min//15
        for t in range(lo,hi):original[action.asset_id][t]=False
    template=replace(inp.template,equipment_availability={a:tuple(v) for a,v in original.items()})
    adjusted=replace(inp,template=template,equipment_availability={a:tuple(v[offset:]) for a,v in original.items()})
    return adjusted.validate()


def check_plan(inp,result,actions,policy,scenarios,maintenance_config=None):
    config=maintenance_config or settings();errors=[]
    by_id={c.candidate_id:c for c in inp.heat_candidates};positions={h.heat_id:i for i,h in enumerate(inp.heats)}
    for action in actions:
        action.validate(config,values(load_config(config['plant_config']))['start'],values(load_config('configs/robustness_v1.yaml'))['horizon_days'])
        begin=pd.Timestamp(action.start_time);end=pd.Timestamp(action.end_time)
        if begin<pd.Timestamp(inp.decision_time):errors.append('Service starts before decision')
        if action.asset_id=='PMP_01':
            for row in result.schedule:
                if pd.Timestamp(row['start'])<end and pd.Timestamp(row['predicted_end'])>begin:errors.append('Pump service intersects nominal heat')
                candidate=by_id[row['candidate_id']]
                for scenario in scenarios:
                    duration=scenario_coefficients(candidate,inp,scenario,positions[row['heat_id']])[1]
                    if pd.Timestamp(row['start'])<end and pd.Timestamp(row['start'])+pd.Timedelta(minutes=duration)>begin:
                        errors.append('Pump service intersects '+scenario.name+' heat')
        for row in result.load_trajectory:
            lo=pd.Timestamp(row['interval_start']);hi=pd.Timestamp(row['interval_end'])
            if hi<=begin or lo>=end:continue
            if row['asset_run'][action.asset_id]:errors.append('Service intersects machine operation')
            if action.asset_id=='MILL_01' and row['rolling_billet_t']>inp.constraints.tolerance:errors.append('Mill service intersects rolling')
            if action.asset_id=='PMP_01' and row['furnace_on']:errors.append('Pump service intersects IF power')
    try:checked=check_robust(_checked_input(inp,actions),result,policy,scenarios)
    except (ValueError,RuntimeError) as exc:return dict(feasible=False,violations=errors+[str(exc)])
    errors.extend(checked['violations'])
    return dict(feasible=not errors,violations=errors,base_robust=checked)


def optimize_maintenance(inp,policy,scenarios,eligible,maintenance_config=None,prior_executed=()):
    cfg=maintenance_config or settings();inp.validate();windows=candidates(inp,eligible,cfg)
    done={x.asset_id for x in prior_executed};windows=tuple(w for w in windows if w.asset_id not in done)
    if not windows:
        b=optimize_robust(inp,policy,scenarios)
        return MaintenancePlan(b.plan,(),(),dict(eligible),b.checker,tuple(b.plan.solver_status.get('stages',())))
    m,co,reason=build_robust_model(inp,policy,scenarios,('practice_loss_40',))
    if m is None:
        result=OptimizerResult('infeasible',False,inp.optimization_mode,inp.objective_mode,reason=reason,forecast_origin=inp.forecast_origin)
        return MaintenancePlan(result,(),windows,dict(eligible),{'feasible':False,'violations':[reason]},())
    m.W=pyo.RangeSet(0,len(windows)-1);m.pm=pyo.Var(m.W,domain=pyo.Binary)
    m.maintenance_constraints=pyo.ConstraintList();n=inp.constraints.horizon_slots
    for asset in ('MILL_01','PMP_01'):
        ids=[i for i,w in enumerate(windows) if w.asset_id==asset]
        if ids:m.maintenance_constraints.add(sum(m.pm[i] for i in ids)<=1)
    for t in m.T:
        for asset in ('MILL_01','PMP_01'):
            active=sum(m.pm[i] for i,w in enumerate(windows) if w.asset_id==asset and pd.Timestamp(w.start_time)<=pd.Timestamp(inp.forecast_origin)+pd.Timedelta(minutes=15*t)<pd.Timestamp(w.end_time))
            if asset=='MILL_01':m.maintenance_constraints.add(m.asset_run[asset,t]+active<=1)
            else:
                _deactivate_constant_pump_equation(m,t)
                available=int(inp.equipment_availability[asset][t] and inp.operating_windows[asset][t])
                m.maintenance_constraints.add(m.pump_on[t]+active==available)
    origin=pd.Timestamp(inp.forecast_origin);positions={h.heat_id:j for j,h in enumerate(inp.heats)}
    duration_vectors=[None]+[{k:scenario_coefficients(v['candidate'],inp,s,positions[v['candidate'].heat_id])[1] for k,v in co.items()} for s in scenarios]
    for i,w in enumerate(windows):
        if w.asset_id!='PMP_01':continue
        left=(pd.Timestamp(w.start_time)-origin).total_seconds()/60;right=left+w.duration_min
        for durations in duration_vectors:
            conflicted=[]
            for k,v in co.items():
                d=v['duration'] if durations is None else durations[k]
                if v['start']<right-inp.constraints.tolerance and v['start']+d>left+inp.constraints.tolerance:conflicted.append(k)
            if conflicted:m.maintenance_constraints.add(sum(m.x[k] for k in conflicted)<=len(inp.heats)*(1-m.pm[i]))
    # Explicit minute-valued planning heuristic: only the 24-h health output is
    # predictive. Conditional failure time uniformity is a marked assumption.
    risk=0
    for asset in ('MILL_01','PMP_01'):
        ids=[i for i,w in enumerate(windows) if w.asset_id==asset]
        if not ids:continue
        p=next(x.calibrated_probability for x in inp.health_predictions if x.asset_id==asset)
        repair=np.mean(values(load_config(cfg['plant_config']))['faults']['repair_hours'])*60
        risk+=p*repair
        for i in ids:
            w=windows[i];lead=min(24,max(0,(pd.Timestamp(w.start_time)-pd.Timestamp(inp.decision_time)).total_seconds()/3600))
            interruption=w.duration_min+cfg['service'][asset]['restart_delay_min']
            risk+=(interruption+p*repair*lead/24-p*repair)*m.pm[i]
    options=inp.constraints.solver_options;solver=Highs();solver.config.load_solution=False
    for package,key in [('pyomo','pyomo_version'),('highspy','highspy_version')]:
        if importlib.metadata.version(package)!=options[key]:raise RuntimeError('Unqualified solver runtime')
    solver.config.time_limit=options['time_limit_seconds'];solver.highs_options=dict(threads=1,random_seed=options['seed'],parallel='off',mip_rel_gap=0,mip_abs_gap=options['absolute_gap'])
    node_limit=values(load_config('configs/robustness_v1.yaml'))['solver_node_limit'];solver.highs_options['mip_max_nodes']=node_limit
    stages=[];answer=None
    for stage in ('feasibility','risk_minutes',inp.objective_mode):
        if stage=='risk_minutes':m.objective.set_value(risk)
        elif stage!='feasibility':set_objective(m,inp)
        solver.config.warmstart=stage!='feasibility'
        try:answer=solver.solve(m)
        except (MemoryError,RuntimeError) as exc:
            result=OptimizerResult('solver_error',False,inp.optimization_mode,inp.objective_mode,reason=str(exc),forecast_origin=inp.forecast_origin)
            return MaintenancePlan(result,(),windows,dict(eligible),{'feasible':False,'violations':[str(exc)]},tuple(stages))
        term=answer.termination_condition.name;feasible=answer.best_feasible_objective is not None and math.isfinite(answer.best_feasible_objective)
        stages.append(dict(stage=stage,termination=term,feasible=feasible))
        if not feasible:
            result=OptimizerResult('infeasible' if term=='infeasible' else 'solver_limit',False,inp.optimization_mode,inp.objective_mode,reason=f'No feasible maintenance continuation at {stage}',forecast_origin=inp.forecast_origin)
            return MaintenancePlan(result,(),windows,dict(eligible),{'feasible':False,'violations':[result.reason]},tuple(stages))
        answer.solution_loader.load_vars()
        if stage=='risk_minutes':
            # Preserve the best available risk value before tariff optimization.
            m.risk_gate=pyo.Constraint(expr=risk<=pyo.value(risk)+1e-6)
    for t in m.T:
        if abs(pyo.value(m.rolling_t[t]))<=inp.constraints.tolerance:m.asset_run['MILL_01',t].set_value(0)
    selected=tuple(w for i,w in enumerate(windows) if pyo.value(m.pm[i])>.5)
    status=dict(termination=term,stages=stages,best_feasible_objective=float(answer.best_feasible_objective),best_objective_bound=None if answer.best_objective_bound is None else float(answer.best_objective_bound),library='Pyomo/HiGHS',node_limit=node_limit)
    result=extract_result(inp,m,co,'optimal' if all(s['termination']=='optimal' for s in stages) else 'feasible',status)
    checked=check_plan(inp,result,selected,policy,scenarios,cfg)
    result=replace(result,releasable=checked['feasible'],checker=checked,status=result.status if checked['feasible'] else 'checker_failed',reason=None if checked['feasible'] else '; '.join(checked['violations']))
    return MaintenancePlan(result,selected,windows,dict(eligible),checked,tuple(stages))
