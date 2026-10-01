"""Immutable narrow supervisor DTOs. Unknown/hidden fields never cross the gateway."""
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json, math, hashlib


class BoundaryError(ValueError): pass
class ServiceUnavailable(RuntimeError): pass


class Mode(str,Enum):
    MONITOR='MONITOR'; PLAN='PLAN'; VERIFY='VERIFY'; RECOMMEND='RECOMMEND'; SIMULATED_EXECUTION='SIMULATED_EXECUTION'


class Disposition(str,Enum):
    PROPOSED='PROPOSED'; VERIFIED='VERIFIED'; APPROVED='APPROVED'; REJECTED='REJECTED'; EXECUTED='EXECUTED'


def stamp(value):
    if not isinstance(value,str):raise BoundaryError('Local ISO timestamp required')
    try:at=datetime.fromisoformat(value)
    except ValueError:raise BoundaryError('Invalid timestamp') from None
    if at.tzinfo is not None:raise BoundaryError('Use declared local naive timestamp')
    return at


def number(value,minimum=0,maximum=None):
    if type(value) not in (int,float) or not math.isfinite(value) or value<minimum or (maximum is not None and value>maximum):
        raise BoundaryError('Invalid finite operational number')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def primitive(value):
    if hasattr(value,'__dataclass_fields__'):return primitive(asdict(value))
    if isinstance(value,Enum):return value.value
    if isinstance(value,dict):return {str(k):primitive(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [primitive(v) for v in value]
    if value is None or type(value) in (str,int,float,bool):return value
    raise BoundaryError('Nonserializable service object')


FORBIDDEN=('latent','wear','fault_label','fault_severity','true_failure','future_event','future_fault',
           'noise_tape','repair_tape','random_tape','events','evaluation_targets','attribution')


def inspect_payload(node):
    """Positive DTO schemas do the primary filtering; this rejects nested smuggling."""
    if isinstance(node,dict):
        for key,value in node.items():
            if any(t in str(key).lower() for t in FORBIDDEN):raise BoundaryError('Hidden/evaluation field rejected')
            inspect_payload(value)
    elif isinstance(node,(tuple,list)):
        for v in node:inspect_payload(v)
    elif isinstance(node,float) and not math.isfinite(node):raise BoundaryError('Nonfinite payload')


@dataclass(frozen=True)
class Observation:
    asset_id:str
    field:str
    value:float|str|None
    available_at:str

    def validate(self,now):
        if self.asset_id not in ('IF_01','RHF_01','MILL_01','PMP_01','CMP_01','AUX','MAIN'):raise BoundaryError('Unknown asset')
        if self.field not in ('kW','kWh','kVA','pf','temp_C','flue_temp_C','vibration_mm_s','rpm','flow_m3_h','pressure_bar','state'):
            raise BoundaryError('Unknown observed channel')
        if stamp(self.available_at)>stamp(now):raise BoundaryError('Future observation')
        if self.value is not None:
            if self.field=='state':
                if type(self.value) is not str or len(self.value)>64:raise BoundaryError('Invalid machine state')
            elif type(self.value) not in (float,int) or not math.isfinite(self.value):raise BoundaryError('Invalid observed value')
        return self


@dataclass(frozen=True)
class PublicSnapshot:
    snapshot_id:str
    timestamp:str
    last_posted_at:str
    production_target_t:float
    inventory_t:float
    observations:tuple[Observation,...]
    completed_heat_ids:tuple[str,...]=()
    untrusted_notes:tuple[str,...]=()
    version:str='public_snapshot_v1'

    def validate(self):
        stamp(self.timestamp);stamp(self.last_posted_at)
        if stamp(self.last_posted_at)>stamp(self.timestamp):raise BoundaryError('Future snapshot')
        number(self.production_target_t);number(self.inventory_t,0,200)
        for row in self.observations:
            if type(row) is not Observation:raise BoundaryError('Typed observations required')
            row.validate(self.timestamp)
        if any(type(t) is not str or len(t)>2000 for t in self.untrusted_notes):raise BoundaryError('Invalid note')
        return self


@dataclass(frozen=True)
class Diagnostics:
    snapshot_id:str
    analytics_version:str
    signals:tuple[str,...]
    measured:tuple[tuple[str,float],...]=()
    no_action_needed:bool=False
    limitations:tuple[str,...]=('Sensor evidence suggests candidates, not true fault diagnoses.',)
    def validate(self):
        for key,value in self.measured:number(value,minimum=-1e9)
        if type(self.no_action_needed) is not bool:raise BoundaryError('Invalid no-action flag')
        return self


@dataclass(frozen=True)
class HeatEstimate:
    heat_id:str
    energy_p50_kWh:float
    energy_p90_kWh:float
    duration_p50_min:float
    duration_p90_min:float
    available_at:str
    def validate(self):
        for v in (self.energy_p50_kWh,self.energy_p90_kWh,self.duration_p50_min,self.duration_p90_min):number(v)
        if self.energy_p90_kWh<self.energy_p50_kWh or self.duration_p90_min<self.duration_p50_min:raise BoundaryError('Quantile ordering')
        stamp(self.available_at);return self


@dataclass(frozen=True)
class HealthRisk:
    asset_id:str
    calibrated_probability:float
    horizon_hours:int
    available_at:str
    def validate(self):
        if self.asset_id not in ('MILL_01','PMP_01') or self.horizon_hours!=24:raise BoundaryError('Unqualified health horizon')
        number(self.calibrated_probability,0,1);stamp(self.available_at);return self


@dataclass(frozen=True)
class PredictionSummary:
    snapshot_id:str
    model_version:str
    schema_sha256:str
    heat_estimates:tuple[HeatEstimate,...]
    aux_p50_kW:tuple[float,...]
    aux_p90_kW:tuple[float,...]
    health_risk:tuple[HealthRisk,...]
    available_at:str
    usable_for_constraints:bool=True
    warnings:tuple[str,...]=('Upper empirical forecast quantiles are not physical guarantees.',)
    def validate(self):
        stamp(self.available_at)
        if self.usable_for_constraints is not True:raise BoundaryError('Unsafe prediction fallback')
        if not self.model_version or len(self.schema_sha256)!=64:raise BoundaryError('Missing prediction version/schema')
        if len(self.aux_p50_kW)!=len(self.aux_p90_kW) or not 1<=len(self.aux_p50_kW)<=96:raise BoundaryError('Incomplete AUX forecast')
        for a,b in zip(self.aux_p50_kW,self.aux_p90_kW):
            number(a);number(b)
            if a>b:raise BoundaryError('AUX quantile ordering')
        if not self.heat_estimates:raise BoundaryError('Missing heat predictions')
        for h in self.heat_estimates:
            h.validate()
            if stamp(h.available_at)>stamp(self.available_at):raise BoundaryError('Future heat prediction')
        if {h.asset_id for h in self.health_risk}!={'MILL_01','PMP_01'}:raise BoundaryError('Missing health predictions')
        for h in self.health_risk:
            h.validate()
            if stamp(h.available_at)>stamp(self.available_at):raise BoundaryError('Future health prediction')
        return self


@dataclass(frozen=True)
class ServiceWindow:
    asset_id:str
    start_time:str
    duration_min:float
    policy_version:str='maintenance_v1'
    def validate(self):
        if self.asset_id not in ('MILL_01','PMP_01'):raise BoundaryError('Unsupported maintenance asset')
        stamp(self.start_time);number(self.duration_min)
        if self.policy_version!='maintenance_v1':raise BoundaryError('Unknown service policy')
        return self


@dataclass(frozen=True)
class MaintenanceSummary:
    snapshot_id:str
    eligible_assets:tuple[str,...]
    candidate_windows:tuple[ServiceWindow,...]
    evidence:tuple[tuple[str,float],...]
    policy_version:str='maintenance_v1'
    def validate(self):
        if self.policy_version!='maintenance_v1' or any(a not in ('MILL_01','PMP_01') for a in self.eligible_assets):raise BoundaryError('Maintenance policy mismatch')
        for s in self.candidate_windows:s.validate()
        for key,v in self.evidence:number(v,0,1)
        return self


@dataclass(frozen=True)
class OptimizationSummary:
    snapshot_id:str
    schedule_id:str
    status:str
    mode:str
    optimizer_feasible:bool
    production_target_t:float
    predicted_energy_kWh:float|None
    predicted_cost_Rs:float|None
    predicted_peak_kVA:float|None
    predicted_SEC:float|None
    reserve_minutes:float
    maintenance_actions:tuple[ServiceWindow,...]
    binding_constraints:tuple[str,...]
    optimizer_version:str='frozen_E4_Phase_F'
    failure_reason:str|None=None
    def validate(self):
        if self.status not in ('FEASIBLE','INFEASIBLE','COMPUTATION_LIMIT','ERROR'):raise BoundaryError('Unknown optimizer status')
        if type(self.optimizer_feasible) is not bool or self.optimizer_feasible!=(self.status=='FEASIBLE'):raise BoundaryError('Contradictory optimization status')
        if self.mode not in ('robust','robust_maintenance','adaptive_robust','adaptive_maintenance'):raise BoundaryError('Unapproved plan mode')
        number(self.production_target_t);number(self.reserve_minutes)
        for v in (self.predicted_energy_kWh,self.predicted_cost_Rs,self.predicted_peak_kVA,self.predicted_SEC):
            if v is not None:number(v)
        if self.optimizer_feasible and any(v is None for v in (self.predicted_energy_kWh,self.predicted_cost_Rs,self.predicted_peak_kVA,self.predicted_SEC)):
            raise BoundaryError('Missing critical predicted metrics')
        for s in self.maintenance_actions:s.validate()
        return self


@dataclass(frozen=True)
class VerificationSummary:
    schedule_id:str
    replay_id:str
    status:str
    physically_valid:bool
    production_complete:bool
    realized_energy_kWh:float|None
    realized_cost_Rs:float|None
    realized_peak_kVA:float|None
    inventory_bounds:tuple[float,float]|None
    violations:tuple[str,...]
    failure_reason:str|None=None
    realized_control_sha256:str|None=None
    def validate(self):
        if self.status not in ('PASS','FAIL','COMPUTATION_LIMIT','UNAVAILABLE'):raise BoundaryError('Unknown replay status')
        if type(self.physically_valid) is not bool or type(self.production_complete) is not bool:raise BoundaryError('Invalid verification flags')
        if self.physically_valid!=(self.status=='PASS'):raise BoundaryError('Contradictory replay result')
        for v in (self.realized_energy_kWh,self.realized_cost_Rs,self.realized_peak_kVA):
            if v is not None:number(v)
        if self.physically_valid:
            if not self.production_complete or self.violations or any(v is None for v in (self.realized_energy_kWh,self.realized_cost_Rs,self.realized_peak_kVA)) or self.inventory_bounds is None:
                raise BoundaryError('Incomplete physical PASS')
            if self.realized_peak_kVA>7000+1e-6:raise BoundaryError('Demand contradiction')
            lo,hi=self.inventory_bounds;number(lo,0,200);number(hi,lo,200)
        return self


@dataclass(frozen=True)
class CheckSummary:
    schedule_id:str
    replay_id:str
    checker_id:str
    passed:bool
    checks:tuple[tuple[str,bool],...]
    def validate(self):
        if type(self.passed) is not bool or not self.checks or any(type(v) is not bool for _,v in self.checks):raise BoundaryError('Malformed independent check')
        if {k for k,_ in self.checks}!={'production','demand','inventory','cooling','material_balance','energy_balance','control_adherence','independent_gate'}:
            raise BoundaryError('Incomplete independent constraint evidence')
        if self.passed!=all(v for _,v in self.checks):raise BoundaryError('Checker status contradiction')
        return self


@dataclass(frozen=True)
class ComparisonSummary:
    schedule_id:str
    reference_id:str
    matched_conditions:bool
    energy_delta_kWh:float|None
    cost_delta_Rs:float|None
    label:str='DIGITAL-TWIN-REALIZED'
    def validate(self):
        if self.label!='DIGITAL-TWIN-REALIZED' or type(self.matched_conditions) is not bool:raise BoundaryError('Comparison label mismatch')
        for v in (self.energy_delta_kWh,self.cost_delta_Rs):
            if v is not None:number(v,-1e12)
        if not self.matched_conditions and (self.energy_delta_kWh is not None or self.cost_delta_Rs is not None):raise BoundaryError('Unmatched numerical comparison')
        return self


@dataclass(frozen=True)
class FailureSummary:
    schedule_id:str
    category:str
    public_reason:str
    permitted_replan_modes:tuple[str,...]
    def validate(self):
        allowed={'duration_accumulation','end_of_day_overrun','no_feasible_continuation','solver_limit',
                 'inventory_or_rolling_availability','pump_IF_interlock','maintenance_conflict','demand_violation','unsupported_control','unknown_failure'}
        if self.category not in allowed:raise BoundaryError('Unknown diagnostic taxonomy')
        if any(m not in ('adaptive_robust','adaptive_maintenance') for m in self.permitted_replan_modes):raise BoundaryError('Unapproved continuation')
        return self


@dataclass(frozen=True)
class EpisodeRequest:
    timestamp:str
    mode:str='RECOMMEND'
    plan_mode:str='robust'
    operator_note:str=''
    def validate(self):
        stamp(self.timestamp);Mode(self.mode)
        if self.plan_mode not in ('robust','robust_maintenance','adaptive_robust','adaptive_maintenance'):raise BoundaryError('Unknown mode')
        if len(self.operator_note)>2000:raise BoundaryError('Oversized note')
        return self


@dataclass(frozen=True)
class SupervisorAction:
    tool:str
    plan_mode:str|None=None
    # No schedule, constraints, values, paths, thresholds or execution arguments.
    def validate(self):
        if self.tool not in ('get_public_snapshot','get_energy_diagnostics','request_predictions','get_maintenance_candidates',
                             'solve_robust_schedule','replay_candidate_plan','check_physical_constraints',
                             'compare_plan_to_reference','get_failure_diagnostics','recommend','escalate','no_action','finish'):
            raise BoundaryError('Unsupported supervisory action')
        if self.plan_mode is not None and self.plan_mode not in ('robust','robust_maintenance','adaptive_robust','adaptive_maintenance'):raise BoundaryError('Unapproved replan mode')
        return self


@dataclass(frozen=True)
class EvidenceRef:
    tool:str
    response_id:str
    response_sha256:str


@dataclass(frozen=True)
class GroundedValue:
    name:str
    value:float
    unit:str
    label:str
    response_id:str
    source_field:str


@dataclass(frozen=True)
class DecisionPacket:
    decision_id:str
    timestamp:str
    disposition:str
    outcome:str
    snapshot:PublicSnapshot|None
    diagnostics:Diagnostics|None
    predictions:PredictionSummary|None
    optimizer_plan:OptimizationSummary|None
    replay_outcome:VerificationSummary|None
    independent_check:CheckSummary|None
    comparison:ComparisonSummary|None
    alternatives_considered:tuple[OptimizationSummary,...]
    recommendation:str
    grounded_values:tuple[GroundedValue,...]
    confidence_notes:tuple[str,...]
    limitations:tuple[str,...]
    required_human_action:str
    provenance:tuple[EvidenceRef,...]
    card_sentences:tuple[tuple[str,tuple[str,...]],...]
    def to_dict(self):return primitive(self)


@dataclass(frozen=True)
class OperatorFeedback:
    decision_id:str
    action:str
    reason_code:str|None=None
    free_text:str|None=None
    def validate(self):
        if self.action not in ('approve','reject','defer'):raise BoundaryError('Unknown feedback action')
        if self.free_text and len(self.free_text)>2000:raise BoundaryError('Oversized feedback')
        return self
