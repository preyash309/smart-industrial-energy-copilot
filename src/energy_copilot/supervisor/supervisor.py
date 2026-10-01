"""Single supervised agent. Numeric explanations and authority stay deterministic."""
from datetime import timedelta
import time
from .contracts import *
from .policy import configuration
from .registry import ToolRegistry
from .audit import AuditLog
from .state_machine import Stage,TOOLS,stage_after
from .decision_packet import packet


class Supervisor:
    def __init__(self,backend,model,config=None):
        self.__backend=backend;self.model=model;self.config=config or configuration()
        self.last_audit=None

    def run(self,request,directory=None):
        audit=AuditLog(directory);self.last_audit=audit
        registry=ToolRegistry(self.__backend,audit,self.config['maximum_response_bytes'])
        state=dict(replans=0,alternatives=[],config_hash=digest(self.config));stage=Stage.SNAPSHOT;reason='Required deterministic service unavailable or invalid'
        outcome='NO_VERIFIED_RECOMMENDATION'
        try:
            request.validate()
            if request.mode=='SIMULATED_EXECUTION' and not self.config['simulated_execution_enabled']:
                raise BoundaryError('Simulated execution disabled; separate approval gateway required')
            audit.append('episode_start',dict(request=primitive(request),prompt_version=self.config['prompt_version'],model=self.model.name,
                live_llm=self.model.is_live_llm,authority=self.config['authority']))
            while stage!=Stage.DONE:
                if audit.metrics['tool_calls']>=self.config['maximum_tool_calls']:raise BoundaryError('Tool-call bound reached')
                tool=TOOLS[stage]
                option=state.get('next_plan_mode',request.plan_mode) if stage==Stage.SOLVE else None
                context=dict(stage=stage.value,request=dict(mode=request.mode,requested_plan_mode=request.plan_mode),
                    required_next_tool=tool,next_plan_mode=option,allowed_actions=[tool,'escalate'],
                    available_plan_modes=self.config['approved_plan_modes'],public_evidence={k:primitive(state[k]) for k in
                        ('snapshot','diagnostics','predictions','maintenance','plan','replay','check','failure') if k in state})
                # Operator text never becomes a trusted instruction, and never enters the model prompt.
                start=time.perf_counter();action=self.model.decide(context,[tool,'escalate']);elapsed=time.perf_counter()-start
                audit.metrics['model_calls']+=1
                if type(action) is not SupervisorAction:raise BoundaryError('Invalid typed model action')
                action.validate()
                usage=getattr(self.model,'last_usage',{})
                if self.model.is_live_llm:
                    audit.metrics['llm_latency_seconds']+=elapsed
                    audit.metrics['input_tokens']+=usage.get('input_tokens',0);audit.metrics['output_tokens']+=usage.get('output_tokens',0)
                audit.append('model_action',dict(action=primitive(action),latency_seconds=elapsed,usage=usage,
                    rationale_summary='Requested an allowlisted deterministic service under the trusted workflow.'))
                if action.tool=='escalate':reason='Supervisor requested operator escalation';break
                if action.tool!=tool:raise BoundaryError('Tool not permitted in current workflow')
                if stage!=Stage.SOLVE and action.plan_mode is not None:raise BoundaryError('Unexpected plan option')
                if stage==Stage.SOLVE:
                    allowed=state['failure'].permitted_replan_modes if 'failure' in state else (request.plan_mode,)
                    chosen=action.plan_mode or option
                    if chosen not in allowed:raise BoundaryError('Unapproved high-level option')
                arguments=({'timestamp':request.timestamp} if stage==Stage.SNAPSHOT else
                    {'snapshot_id':state['snapshot'].snapshot_id,'plan_mode':chosen} if stage==Stage.SOLVE else
                    {'snapshot_id':state['snapshot'].snapshot_id} if stage in (Stage.DIAGNOSTICS,Stage.PREDICT,Stage.MAINTENANCE) else
                    {'replay_id':state['replay'].replay_id} if stage==Stage.CHECK else {'schedule_id':state['plan'].schedule_id})
                response,ref=registry.call(tool,arguments)
                name={Stage.SNAPSHOT:'snapshot',Stage.DIAGNOSTICS:'diagnostics',Stage.PREDICT:'predictions',Stage.MAINTENANCE:'maintenance',
                      Stage.SOLVE:'plan',Stage.REPLAY:'replay',Stage.CHECK:'check',Stage.COMPARE:'comparison',Stage.FAILURE:'failure'}[stage]
                state[name]=response;state[name+'_ref']=ref
                if stage==Stage.SNAPSHOT:
                    if response.timestamp!=request.timestamp or stamp(request.timestamp)-stamp(response.last_posted_at)>timedelta(minutes=self.config['maximum_state_age_min']):
                        raise BoundaryError('Stale or mismatched public snapshot')
                elif stage in (Stage.DIAGNOSTICS,Stage.PREDICT,Stage.MAINTENANCE,Stage.SOLVE):
                    if response.snapshot_id!=state['snapshot'].snapshot_id:raise BoundaryError('Snapshot identity mismatch')
                    if stage==Stage.PREDICT:
                        if response.model_version!=self.config['prediction_model_version'] or response.schema_sha256!=self.config['prediction_schema_sha256']:
                            raise BoundaryError('Frozen prediction model/schema mismatch')
                        age=stamp(request.timestamp)-stamp(response.available_at)
                        if age<timedelta(0):raise BoundaryError('Future prediction')
                        if age>timedelta(minutes=self.config['maximum_state_age_min']):raise BoundaryError('Stale prediction')
                    if stage==Stage.SOLVE:
                        if response.production_target_t!=state['snapshot'].production_target_t:raise BoundaryError('Production target changed')
                        if response.mode!=chosen:raise BoundaryError('Plan mode mismatch')
                        if any(p.schedule_id==response.schedule_id for p in state['alternatives']):
                            state['unchanged_candidate']=True
                            audit.append('escalation',dict(reason='Deterministic replan returned an unchanged rejected candidate',schedule_id=response.schedule_id))
                            reason='Deterministic replan returned an unchanged rejected candidate; operator escalation required'
                            break
                        state['alternatives'].append(response)
                        state.pop('replay',None);state.pop('check',None)
                elif stage in (Stage.REPLAY,Stage.CHECK,Stage.COMPARE,Stage.FAILURE):
                    if response.schedule_id!=state['plan'].schedule_id:raise BoundaryError('Schedule identity mismatch')
                    if stage==Stage.CHECK and response.replay_id!=state['replay'].replay_id:raise BoundaryError('Replay identity mismatch')
                audit.append('transition',dict(stage=stage.value,response_id=ref.response_id))
                stage=stage_after(stage,state,request,self.config)
                audit.metrics['replans']=state['replans']
            plan=state.get('plan');replay=state.get('replay');check=state.get('check')
            if stage==Stage.DONE and plan and plan.optimizer_feasible and replay and replay.physically_valid and check and check.passed:
                outcome='VERIFIED_ANALYSIS' if request.mode=='VERIFY' else 'VERIFIED_RECOMMENDATION';reason='Independent physical gate passed'
            elif stage==Stage.DONE and state.get('diagnostics') and state['diagnostics'].no_action_needed:
                outcome='NO_ACTION_NEEDED';reason='No operating change requested by deterministic diagnostics'
            elif stage==Stage.DONE and request.mode=='MONITOR':outcome='MONITOR_ONLY';reason='Monitoring authority only'
            elif stage==Stage.DONE and request.mode=='PLAN' and plan and plan.optimizer_feasible:outcome='PLAN_ONLY';reason='Physical verification still required'
            elif state.get('failure') and not state.get('unchanged_candidate'):
                reason=state['failure'].public_reason
                if state['failure'].category=='solver_limit':reason='No accepted continuation was obtained within the configured solve limit.'
        except (BoundaryError,ServiceUnavailable,ValueError,TypeError) as exc:
            reason=str(exc);outcome='NO_VERIFIED_RECOMMENDATION'
            audit.append('escalation',dict(reason=reason,exception_type=type(exc).__name__))
        except Exception as exc:
            reason='Required service failed unexpectedly; operator escalation required'
            outcome='NO_VERIFIED_RECOMMENDATION'
            audit.append('escalation',dict(reason=reason,exception_type=type(exc).__name__))
        answer=packet(request,state,registry,outcome,reason)
        # A grounded card cannot gain new numbers from model prose.
        for v in answer.grounded_values:
            ref=registry.evidence[v.response_id];registry.grounded(ref,v.source_field,v.value)
        audit.finish(answer);audit.verify_chain();return answer
