"""Capability facade: fixed tools and narrow arguments; no filesystem/execute tool."""
from .contracts import *
import time

RESPONSES={'get_public_snapshot':PublicSnapshot,'get_energy_diagnostics':Diagnostics,'request_predictions':PredictionSummary,
           'get_maintenance_candidates':MaintenanceSummary,'solve_robust_schedule':OptimizationSummary,
           'replay_candidate_plan':VerificationSummary,'check_physical_constraints':CheckSummary,
           'compare_plan_to_reference':ComparisonSummary,'get_failure_diagnostics':FailureSummary}
ARGUMENTS={'get_public_snapshot':{'timestamp'},'get_energy_diagnostics':{'snapshot_id'},'request_predictions':{'snapshot_id'},
           'get_maintenance_candidates':{'snapshot_id'},'solve_robust_schedule':{'snapshot_id','plan_mode'},
           'replay_candidate_plan':{'schedule_id'},'check_physical_constraints':{'replay_id'},
           'compare_plan_to_reference':{'schedule_id'},'get_failure_diagnostics':{'schedule_id'}}


class ToolRegistry:
    def __init__(self,backend,audit,maximum_bytes=262144):
        self.__backend=backend;self.audit=audit;self.maximum_bytes=maximum_bytes;self.evidence={};self.values={}

    def call(self,name,arguments):
        if name not in RESPONSES or set(arguments)!=ARGUMENTS[name]:raise BoundaryError('Unknown tool or arguments')
        inspect_payload(arguments)
        self.audit.metrics['tool_calls']+=1
        if name=='solve_robust_schedule':self.audit.metrics['optimizer_calls']+=1
        if name=='replay_candidate_plan':self.audit.metrics['replay_calls']+=1
        started=time.perf_counter()
        try:
            answer=self.__backend.call(name,dict(arguments))
            if type(answer) is not RESPONSES[name]:raise BoundaryError('Invalid typed tool response')
            answer.validate();payload=primitive(answer);inspect_payload(payload)
            encoded=__import__('json').dumps(payload,allow_nan=False)
            if len(encoded.encode())>self.maximum_bytes:raise BoundaryError('Oversized tool response')
            response_id='tool_'+digest(dict(tool=name,args=arguments,response=payload))[:24]
            ref=EvidenceRef(name,response_id,digest(payload));self.evidence[response_id]=ref;self.values[response_id]=payload
            self.audit.append('tool_result',dict(tool=name,arguments=arguments,response=payload,response_id=response_id,
                response_sha256=ref.response_sha256,latency_seconds=time.perf_counter()-started))
            return answer,ref
        except Exception as exc:
            self.audit.metrics['failed_tool_calls']+=1
            # Exceptions from execution may contain hidden implementation details.
            self.audit.append('tool_failure',dict(tool=name,arguments=arguments,error_type=type(exc).__name__,
                                                reason='Required deterministic service unavailable or invalid',latency_seconds=time.perf_counter()-started))
            if isinstance(exc,BoundaryError):raise BoundaryError('Invalid typed service response or information-boundary violation') from None
            raise ServiceUnavailable('Required deterministic service unavailable or invalid') from None

    def grounded(self,ref,field,value):
        if ref.response_id not in self.values or self.values[ref.response_id].get(field)!=value:raise BoundaryError('Unsupported critical number')
        return True
