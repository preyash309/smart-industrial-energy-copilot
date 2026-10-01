"""Trusted deterministic gateway, NOT agent/model code.

Public past alone feeds PredictionService/optimizers. Matched replay and hidden
checker tables remain private here; only explicit aggregate DTOs cross the facade.
"""
from dataclasses import replace
from pathlib import Path
import json
import pandas as pd
from energy_copilot.common import load_config,values,write_json,sha256
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization.contracts import input_from_dict
from energy_copilot.robust.state_update import public_snapshot,update_state,remaining_input
from energy_copilot.robust.contracts import ReservePolicy
from energy_copilot.robust.scenarios import make_scenarios
from energy_copilot.robust.robust_model import optimize_robust
from energy_copilot.maintenance.optimizer import optimize_maintenance,candidates
from energy_copilot.maintenance.policy import eligible_assets,MaintenancePolicy
from energy_copilot.maintenance.controller import run_maintenance
from energy_copilot.maintenance.evaluation import evaluate_controller
from energy_copilot.maintenance.checker import verify_maintenance
from energy_copilot.maintenance.execution import simulate
from energy_copilot.maintenance.contracts import MaintenanceAction
from energy_copilot.replay.adapter import ReplayControls
from energy_copilot.replay.origin_state import before_origin
from energy_copilot.replay.compare import realized_metrics
from .contracts import *


def failure_category(reason,status=None):
    s=(reason or '').lower()
    if status in ('solver_limit','COMPUTATION_LIMIT'):return 'solver_limit'
    if 'working day' in s or 'end-of-day' in s:return 'end_of_day_overrun'
    if 'occupancy' in s or 'overlap' in s and 'heat' in s:return 'duration_accumulation'
    if 'pump' in s and ('interlock' in s or 'powered' in s):return 'pump_IF_interlock'
    if 'service' in s and ('conflict' in s or 'overlap' in s):return 'maintenance_conflict'
    if 'inventory' in s or 'rolling' in s:return 'inventory_or_rolling_availability'
    if 'demand' in s:return 'demand_violation'
    if 'unsupported' in s:return 'unsupported_control'
    return 'no_feasible_continuation'


REASONS={'solver_limit':'No accepted continuation was obtained within the configured solve limit.',
 'end_of_day_overrun':'The represented heat execution exceeded the working-day window.',
 'duration_accumulation':'Accumulated heat-duration uncertainty consumed the remaining scheduling window.',
 'pump_IF_interlock':'Cooling/induction-furnace interlock rejected the candidate.',
 'maintenance_conflict':'A selected service conflicted with represented operation.',
 'inventory_or_rolling_availability':'Inventory or rolling availability rejected the candidate.',
 'demand_violation':'Independent demand checks rejected the candidate.',
 'unsupported_control':'The deterministic service rejected an unsupported control.',
 'no_feasible_continuation':'No accepted continuation was obtained; escalate the retained outcome.'}


def check_summary(schedule_id,replay_id,checked):
    raw=checked['checks']
    def all_matching(tokens):return all(v==0 for k,v in raw.items() if any(t in k for t in tokens))
    flags=dict(production=all_matching(('production','daily_bar','daily_billet','heats_per','replay_bar_order','replay_billet_order')),
        demand=all_matching(('demand',)),inventory=all_matching(('inventory','stock','reserve')),
        cooling=all_matching(('cooling','pump_interlock','service_')),
        material_balance=all_matching(('mass','yield','caster','melt','rolling_mass')),
        energy_balance=all_matching(('energy','kWh','main_P','fuel','coal')),
        control_adherence=all_matching(('exact','permissive','service_')),
        independent_gate=bool(checked['feasible'] and checked['violations']==0))
    return CheckSummary(schedule_id,replay_id,'check_'+digest(flags)[:20],all(flags.values()),tuple(flags.items())).validate()


class StackBackend:
    """One trusted host-bound seed/day; agent cannot select seed, files or physics."""
    def __init__(self,baseline,template,seed,days,worker_output):
        self.__baseline=baseline;self.__config=baseline.config;self.__seed=seed;self.__days=days
        self.__service=PredictionService('models/phase2b_v1')
        self.__origin=template.forecast_origin;self.__template=template;self.__output=Path(worker_output)
        self.__output.mkdir(parents=True,exist_ok=True)
        # Project first, including production posting-time gates. No label columns.
        self.__public=public_snapshot(baseline,self.__origin)
        from energy_copilot.replay.history import seed_input
        self.__day_input,_=seed_input(template,*self.__public,values(self.__config),self.__service)
        self.__state=update_state(None,self.__origin,self.__public[1],[],[],self.__day_input)
        self.__input,self.__posting=remaining_input(self.__day_input,self.__state,self.__public,values(self.__config),self.__service,grid=1)
        freeze=json.loads(Path('replay/robustness_v1/design_freeze.json').read_text())
        self.__reserve=ReservePolicy(**freeze['policy'])
        self.__calibration=json.loads(Path('replay/robustness_v1/duration_calibration.json').read_text())
        from scripts.phase2f import frozen_policy
        self.__maintenance_policy=frozen_policy()
        self.__eligible,self.__health_audit=eligible_assets(self.__input.health_predictions,self.__public[0],self.__origin,self.__maintenance_policy)
        self.__snapshot_id='snapshot_'+digest(dict(origin=self.__origin,source_seed=seed,public_last_heat=list(self.__public[1].heat_id.tail(1))))[:24]
        self.__plans={};self.__replays={};self.__reference=None

    @classmethod
    def fresh_scenario(cls,seed,day,worker_output):
        if seed not in (3001,3002,3003):raise BoundaryError('Host integration scenarios are predeclared; no upstream final tuning')
        from energy_copilot.sim import simulate as frozen_simulate
        cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml');baseline=frozen_simulate(cfg,seed=seed,days=30)
        template=input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))
        delta=pd.Timedelta(days=day-7)
        template=replace(template,forecast_origin=(pd.Timestamp(template.forecast_origin)+delta).isoformat(),
            heats=tuple(replace(h,heat_id=h.heat_id.replace('D007',f'D{day:03d}')) for h in template.heats),
            tariff_calendar=tuple(replace(t,interval_start=(pd.Timestamp(t.interval_start)+delta).isoformat(),
                                        interval_end=(pd.Timestamp(t.interval_end)+delta).isoformat()) for t in template.tariff_calendar))
        return cls(baseline,template,seed,30,worker_output)

    def __snapshot(self):
        r=self.__public[0];at=self.__origin;latest=r.sort_values('timestamp').groupby('asset_id').tail(1)
        rows=[];fields=('kW','kWh','kVA','pf','temp_C','flue_temp_C','vibration_mm_s','rpm','flow_m3_h','pressure_bar','state')
        for row in latest.itertuples():
            posted=(row.timestamp+pd.Timedelta(minutes=15)).isoformat()
            for field in fields:
                v=getattr(row,field)
                if field!='state':v=None if pd.isna(v) or row.sensor_glitch else float(v)
                rows.append(Observation(row.asset_id,field,v,posted))
        return PublicSnapshot(self.__snapshot_id,at,(r.timestamp.max()+pd.Timedelta(minutes=15)).isoformat(),
            self.__template.production_order.bars_t,self.__state.actual_inventory_t,tuple(rows),self.__state.completed_heats)

    def __predictions(self):
        hs=[]
        for h in self.__input.heats:
            p=next(k.prediction for k in self.__input.heat_candidates if k.heat_id==h.heat_id)
            hs.append(HeatEstimate(h.heat_id,p.energy_p50_kWh,p.energy_p90_kWh,p.duration_p50_min,p.duration_p90_min,p.available_at))
        load=self.__input.background_load_forecast
        hp=tuple(HealthRisk(p.asset_id,p.calibrated_probability,p.horizon_hours,p.available_at) for p in self.__input.health_predictions)
        return PredictionSummary(self.__snapshot_id,self.__input.prediction_version,self.__input.prediction_schema_sha256,tuple(hs),
            tuple(p.load_p50_kW for p in load),tuple(p.load_p90_kW for p in load),hp,self.__origin)

    def __solve(self,mode):
        scenarios=make_scenarios(self.__calibration,self.__state.remaining_heats)
        if 'maintenance' in mode:
            solved=optimize_maintenance(self.__input,self.__reserve,scenarios,self.__eligible)
            actions=solved.actions
        else:solved=optimize_robust(self.__input,self.__reserve,scenarios);actions=()
        p=solved.plan;identity='schedule_'+digest(dict(plan=p.to_dict(),mode=mode,snapshot=self.__snapshot_id))[:24]
        self.__plans[identity]=(mode,solved,actions)
        write_json(self.__output/(identity+'.json'),solved.to_dict())
        status='FEASIBLE' if p.releasable else 'COMPUTATION_LIMIT' if p.status=='solver_limit' else 'INFEASIBLE' if p.status=='infeasible' else 'ERROR'
        m=p.predicted_metrics
        service=tuple(ServiceWindow(a.asset_id,a.start_time,a.duration_min) for a in actions)
        return OptimizationSummary(self.__snapshot_id,identity,status,mode,p.releasable,self.__template.production_order.bars_t,
            m.get('predicted_total_kWh'),m.get('predicted_tariff_cost_Rs'),m.get('predicted_peak_kVA_bound'),m.get('predicted_IF_SEC_kWh_per_t'),
            self.__reserve.end_margin_min,service,tuple(k for k in p.active_constraints if k.startswith('binding_')),
            failure_reason=None if p.releasable else REASONS[failure_category(p.reason,p.status)])

    def __controls(self,result):
        # Pure translation of checked deterministic decisions, no physical coefficients.
        day=(pd.Timestamp(self.__origin)-pd.Timestamp(values(self.__config)['start'])).days
        schedule={r['heat_id']:r['start'] for r in result.schedule}
        modes={r['selected_practice'] for r in result.schedule}
        if modes!={'practice_loss_40'}:raise BoundaryError('Frozen E4 practice mode changed')
        practice={day:self.__service.contract['practice_modes']['practice_loss_40']['practice_loss_kWh_t']}
        dispatch={day*96+i:r['rolling_billet_t'] for i,r in enumerate(result.load_trajectory)}
        return ReplayControls(schedule,practice,dispatch,'Frozen robust exact controls',self.__origin,
            (pd.Timestamp(self.__origin)+pd.Timedelta(days=1)).isoformat())

    def __replay(self,identity):
        prior=next((r for r in self.__replays.values() if r[0]==identity),None)
        if prior is not None:
            # Frozen inputs are deterministic. Reuse immutable evidence, never overwrite it.
            output=self.__output/identity/'public_verification_summary.json'
            data=json.loads(output.read_text())
            data['violations']=tuple(data['violations'])
            if data['inventory_bounds'] is not None:data['inventory_bounds']=tuple(data['inventory_bounds'])
            return VerificationSummary(**data).validate()
        mode,solved,actions=self.__plans[identity];p=solved.plan
        if not p.releasable:raise BoundaryError('Optimizer did not release candidate')
        output=self.__output/identity;output.mkdir(exist_ok=False)
        controls=self.__controls(p);sim=None;checked=None;metrics=None;status='FAIL';reason=None
        if mode.startswith('adaptive'):
            strategy='F2' if mode=='adaptive_maintenance' else 'F0'
            controller,controls=run_maintenance(self.__day_input,self.__config,self.__seed,self.__days,self.__service,
                self.__reserve,self.__calibration,self.__maintenance_policy,output/'controller',strategy=strategy,grid=1)
            actions=tuple(MaintenanceAction(**a) for a in controller['maintenance_actions'])
            entry,sim=evaluate_controller(strategy,self.__baseline,self.__day_input,controller,controls,self.__seed,self.__days,
                                          output/'controller',actions)
            if entry['status']=='physically_valid':checked=entry['verification'];metrics=entry['realized_metrics'];status='PASS'
            else:
                plans=list((output/'controller').glob('replan_step_*.json'))
                last=json.loads(sorted(plans)[-1].read_text()) if plans else json.loads((output/'controller'/'initial_plan.json').read_text())
                category=failure_category(entry.get('reason'),last.get('status'))
                status='COMPUTATION_LIMIT' if category=='solver_limit' else 'FAIL';reason=REASONS[category]
        else:
            try:
                sim=simulate(self.__config,schedule=controls.schedule,practice_by_day=controls.practice_by_day,
                    rolling_dispatch=controls.rolling_dispatch,seed=self.__seed,days=self.__days,maintenance_actions=actions)
                checked=verify_maintenance(sim,self.__day_input,actions,controls,
                    original_exogenous_sha256=self.__baseline.scenario_manifest['scenario_sha256'])
                if before_origin(sim,self.__origin)!=before_origin(self.__baseline,self.__origin):raise BoundaryError('Matched pre-origin state differs')
                if checked['feasible']:metrics,_=realized_metrics(sim,self.__day_input,checked['physical']);status='PASS'
                else:reason='Independent physical checks rejected candidate'
            except (ValueError,RuntimeError) as exc:reason=REASONS[failure_category(str(exc))]
        replay_id='replay_'+digest(dict(schedule=identity,controls=controls.sha256,status=status))[:24]
        self.__replays[replay_id]=(identity,sim,actions,controls,metrics,checked,status,reason)
        if sim is not None:sim.write(output/'physical_evaluation_only')
        if checked:write_json(output/'independent_check.json',checked)
        m=metrics or {};v=VerificationSummary(identity,replay_id,status,status=='PASS',status=='PASS',m.get('total_kWh'),
            m.get('physical_evaluation_tariff_cost_Rs'),m.get('peak_piecewise_kVA'),
            (m['inventory_min_t'],m['inventory_max_t']) if metrics else None,() if status=='PASS' else ('physical_acceptance_failed',),reason,controls.sha256)
        write_json(output/'public_verification_summary.json',primitive(v));return v

    def __check(self,replay_id):
        identity,sim,actions,controls,metrics,prior,status,reason=self.__replays[replay_id]
        if status!='PASS' or sim is None:raise BoundaryError('No complete physical replay to check')
        checked=verify_maintenance(sim,self.__day_input,actions,controls,
            original_exogenous_sha256=self.__baseline.scenario_manifest['scenario_sha256'])
        return check_summary(identity,replay_id,checked)

    def __compare(self,identity):
        row=next((x for x in self.__replays.values() if x[0]==identity and x[6]=='PASS'),None)
        if row is None:raise BoundaryError('No verified candidate for comparison')
        if self.__reference is None:
            day=(pd.Timestamp(self.__origin)-pd.Timestamp(values(self.__config)['start'])).days
            practice=self.__service.contract['practice_modes']['practice_loss_40']['practice_loss_kWh_t']
            baseline=simulate(self.__config,seed=self.__seed,days=self.__days,practice_by_day={day:practice})
            checked=verify_maintenance(baseline,self.__day_input,(),original_exogenous_sha256=self.__baseline.scenario_manifest['scenario_sha256'])
            if not checked['feasible']:raise BoundaryError('Reference replay not accepted')
            self.__reference=realized_metrics(baseline,self.__day_input,checked['physical'])[0]
            write_json(self.__output/'reference_physical_evaluation_only.json',self.__reference)
        a=self.__reference;b=row[4]
        return ComparisonSummary(identity,'reference_'+self.__snapshot_id,True,b['total_kWh']-a['total_kWh'],
                                 b['physical_evaluation_tariff_cost_Rs']-a['physical_evaluation_tariff_cost_Rs'])

    def execute_approved_simulation(self,identity):
        """Host-only callback AFTER ApprovalGateway approval; absent from tool registry."""
        row=next((r for r in self.__replays.values() if r[0]==identity and r[6]=='PASS'),None)
        if row is None:raise BoundaryError('No accepted execution controls')
        _,_,actions,controls,_,_,_,_=row
        executed=simulate(self.__config,schedule=controls.schedule,practice_by_day=controls.practice_by_day,
            rolling_dispatch=controls.rolling_dispatch,seed=self.__seed,days=self.__days,maintenance_actions=actions)
        checked=verify_maintenance(executed,self.__day_input,actions,controls,
            original_exogenous_sha256=self.__baseline.scenario_manifest['scenario_sha256'])
        if not checked['feasible'] or before_origin(executed,self.__origin)!=before_origin(self.__baseline,self.__origin):
            raise BoundaryError('Approved simulation failed independent execution checks')
        destination=self.__output/('approved_simulation_'+identity)
        executed.write(destination)
        return dict(schedule_id=identity,status='EXECUTED',scope='SIMULATED-EXECUTION-ONLY',
            control_sha256=controls.sha256,independent_check_passed=True)

    def call(self,tool,args):
        if 'snapshot_id' in args and args['snapshot_id']!=self.__snapshot_id:raise BoundaryError('Unknown snapshot identity')
        if tool=='get_public_snapshot':
            if args['timestamp']!=self.__origin:raise BoundaryError('Host-bound as-of timestamp mismatch')
            return self.__snapshot()
        if tool=='get_energy_diagnostics':
            r=self.__public[0];h=self.__public[1]
            sec=float(h.kWh.sum()/h.liquid_t.sum());duration=float((h.end-h.start).dt.total_seconds().mean()/60)
            return Diagnostics(self.__snapshot_id,'analytics_v1',('Historical sensor/register context; no true fault diagnosis.',),
                               (('historical_IF_SEC_kWh_per_t',sec),('historical_heat_duration_min',duration)))
        if tool=='request_predictions':return self.__predictions()
        if tool=='get_maintenance_candidates':
            windows=candidates(self.__input,self.__eligible)
            return MaintenanceSummary(self.__snapshot_id,tuple(a for a,v in self.__eligible.items() if v),
                tuple(ServiceWindow(w.asset_id,w.start_time,w.duration_min) for w in windows),
                tuple((r['asset_id'],r['calibrated_probability']) for r in self.__health_audit))
        if tool=='solve_robust_schedule':return self.__solve(args['plan_mode'])
        if tool=='replay_candidate_plan':return self.__replay(args['schedule_id'])
        if tool=='check_physical_constraints':return self.__check(args['replay_id'])
        if tool=='compare_plan_to_reference':return self.__compare(args['schedule_id'])
        if tool=='get_failure_diagnostics':
            identity=args['schedule_id'];mode,solved,actions=self.__plans[identity]
            row=next((r for r in reversed(list(self.__replays.values())) if r[0]==identity),None)
            category=failure_category(row[7],row[6]) if row else failure_category(solved.plan.reason,solved.plan.status)
            permitted=() if category in ('solver_limit','unsupported_control','demand_violation') else ('adaptive_robust',)
            # Maintenance-conflict alternatives disable maintenance, not interlocks.
            return FailureSummary(identity,category,REASONS[category],permitted)
        raise BoundaryError('Unknown deterministic service')
