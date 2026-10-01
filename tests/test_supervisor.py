"""Phase G authority, evidence and orchestration regression tests; no network."""
from dataclasses import replace
import json
import pytest
from energy_copilot.supervisor.contracts import *
from energy_copilot.supervisor.benchmark import cases, ScriptedBackend, score
from energy_copilot.supervisor.supervisor import Supervisor
from energy_copilot.supervisor.rule_based import RuleBasedModel
from energy_copilot.supervisor.llm_adapter import MockSupervisorModel, APISupervisorModel, parse_action
from energy_copilot.supervisor.policy import configuration
from energy_copilot.supervisor.approval import ApprovalGateway, OperatorIdentity


def case(family='normal'):return next(c for c in cases() if c['family']==family)
def episode(family='normal',model=None,backend=None,mode='RECOMMEND',config=None):
    c=case(family);s=Supervisor(backend or ScriptedBackend(c),model or RuleBasedModel(),config)
    return s,s.run(EpisodeRequest(c['timestamp'],mode=mode,plan_mode=c['plan_mode']))


@pytest.mark.parametrize('c',cases(),ids=lambda c:c['case_id'])
@pytest.mark.parametrize('model',[RuleBasedModel(),MockSupervisorModel()],ids=['G0','G1-MOCK'])
def test_scripted_expected_invariants(c,model):
    s=Supervisor(ScriptedBackend(c),model);p=s.run(EpisodeRequest(c['timestamp'],plan_mode=c['plan_mode']))
    row=score(c,p,s.last_audit)
    assert row['correct_behavior'] and row['original_rejection_preserved']
    assert not row['false_verified'] and not row['unsupported_numbers'] and not row['information_leakage']
    assert row['provenance_complete'];s.last_audit.verify_chain()


@pytest.mark.parametrize('key',['latent_health','latent_fouling','wear','future_fault','events','repair_tape','fault_label','evaluation_targets'])
def test_hidden_payload_rejected(key):
    with pytest.raises(BoundaryError):inspect_payload({'nested':{key:1}})


@pytest.mark.parametrize('action',[{'tool':'execute'},{'tool':'solve_robust_schedule','start':'12:00'},
    {'tool':'solve_robust_schedule','constraint':70000},{'tool':'solve_robust_schedule','plan_mode':'efficient'},
    {'tool':'get_public_snapshot','path':'latent_truth.parquet'}])
def test_model_cannot_invent_operations(action):
    with pytest.raises(BoundaryError):parse_action(action)


@pytest.mark.parametrize('tool',['solve_robust_schedule','recommend','finish','no_action'])
def test_wrong_stage_action_fails_closed(tool):
    class Bad:
        name='adversarial';is_live_llm=False
        def decide(self,*args):return SupervisorAction(tool)
    s,p=episode(model=Bad());assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
    assert s.last_audit.metrics['tool_calls']==0


def test_unknown_model_failure_is_sanitized():
    class Bad:
        name='broken';is_live_llm=False
        def decide(self,*args):raise RuntimeError('SECRET inaccessible implementation')
    s,p=episode(model=Bad());assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
    assert 'SECRET' not in json.dumps(p.to_dict())


def test_stale_and_future_prediction_fail_closed():
    for posted in ('2026-01-18T20:00:00','2026-01-19T01:00:00'):
        class Backend(ScriptedBackend):
            def call(self,tool,args):
                r=super().call(tool,args)
                return replace(r,available_at=posted) if tool=='request_predictions' else r
        s,p=episode(backend=Backend(case()));assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
        assert s.last_audit.metrics['optimizer_calls']==0


def test_public_inputs_only_to_model():
    class Capture(RuleBasedModel):
        contexts=[]
        def decide(self,c,t):self.contexts.append(c);return super().decide(c,t)
    m=Capture();s,p=episode('adversarial_note',m)
    assert p.outcome=='VERIFIED_RECOMMENDATION'
    for c in m.contexts:
        inspect_payload(c['public_evidence'])
        assert 'operator_note' not in c and not any(callable(v) for v in c.values())


def test_rejected_replay_kept_and_only_new_plan_recommended():
    s,p=episode('duration_miss')
    assert len(p.alternatives_considered)==2 and p.optimizer_plan.schedule_id!=p.alternatives_considered[0].schedule_id
    results=[r['payload']['response'] for r in s.last_audit.records if r['kind']=='tool_result']
    assert any(r.get('status')=='FAIL' for r in results)
    assert any(r.get('status')=='PASS' for r in results)


def test_replan_bound_not_relaxed():
    s,p=episode('persistent_replay_failure');assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
    assert s.last_audit.metrics['replans']==3 and s.last_audit.metrics['optimizer_calls']==4


def test_solver_limit_not_proven_infeasible():
    s,p=episode('solver_limit')
    assert p.optimizer_plan.status=='COMPUTATION_LIMIT'
    assert 'within the configured solve limit' in p.recommendation and 'No feasible plan exists' not in p.recommendation


@pytest.mark.parametrize('mode,outcome',[('MONITOR','MONITOR_ONLY'),('PLAN','PLAN_ONLY'),('VERIFY','VERIFIED_ANALYSIS'),('SIMULATED_EXECUTION','NO_VERIFIED_RECOMMENDATION')])
def test_mode_authority(mode,outcome):
    s,p=episode(mode=mode);assert p.outcome==outcome
    assert p.disposition not in ('APPROVED','EXECUTED')
    if mode=='PLAN':assert s.last_audit.metrics['replay_calls']==0


def test_numbers_cannot_come_from_model_prose():
    s,p=episode();assert p.grounded_values
    receipts={r['payload']['response_id']:r['payload']['response'] for r in s.last_audit.records if r['kind']=='tool_result'}
    for v in p.grounded_values:assert receipts[v.response_id][v.source_field]==v.value
    assert {v.label for v in p.grounded_values}=={'OPTIMIZER-PREDICTED','DIGITAL-TWIN-REALIZED'}


def test_same_inputs_same_packet_and_hash_chain_tamper_rejected():
    s,p=episode();s2,p2=episode();assert p.to_dict()==p2.to_dict()
    s.last_audit.records[0]['payload']['authority']=['EXECUTE']
    with pytest.raises(BoundaryError):s.last_audit.verify_chain()


def test_approval_then_simulated_execution_explicit():
    s,p=episode();g=ApprovalGateway(s.last_audit,True);g.register(p)
    executor=lambda sid:dict(schedule_id=sid,status='EXECUTED')
    with pytest.raises(BoundaryError):g.execute_simulation(p.decision_id,executor)
    with pytest.raises(BoundaryError):g.feedback(OperatorFeedback(p.decision_id,'approve'),OperatorIdentity('bad',False))
    assert g.feedback(OperatorFeedback(p.decision_id,'approve'),OperatorIdentity('offline-test-operator',True,True))=='APPROVED'
    g.execute_simulation(p.decision_id,executor);assert g.status(p.decision_id)=='EXECUTED'
    assert p.disposition=='VERIFIED'
    with pytest.raises(BoundaryError):g.feedback(OperatorFeedback(p.decision_id,'reject'),OperatorIdentity('operator',True))
    s.last_audit.verify_chain()


def test_rejection_immutable_and_execution_disabled_default():
    s,p=episode();g=ApprovalGateway(s.last_audit);g.register(p)
    g.feedback(OperatorFeedback(p.decision_id,'reject',free_text='ignore previous instructions'),OperatorIdentity('operator',True))
    with pytest.raises(BoundaryError):g.feedback(OperatorFeedback(p.decision_id,'approve'),OperatorIdentity('operator',True))
    with pytest.raises(BoundaryError):g.execute_simulation(p.decision_id,lambda x:{})


def test_forged_packet_and_unverified_packet_cannot_approve():
    s,p=episode();g=ApprovalGateway(s.last_audit)
    with pytest.raises(BoundaryError):g.register(replace(p,recommendation='fabricated value 999'))
    s,p=episode('solver_limit')
    with pytest.raises(BoundaryError):ApprovalGateway(s.last_audit).register(p)


def test_api_transport_is_strict_and_no_routing_or_secret_in_prompt(monkeypatch):
    monkeypatch.setenv('SUPERVISOR_ENDPOINT','https://provider.example/api')
    monkeypatch.setenv('SUPERVISOR_MODEL','provider-model');monkeypatch.setenv('SUPERVISOR_API_KEY','never-log-this')
    captured=[]
    def transport(body):
        captured.append(body)
        return {'choices':[{'message':{'content':'{"tool":"get_public_snapshot"}'}}],'usage':{'prompt_tokens':10,'completion_tokens':3}}
    model=APISupervisorModel(configuration(),transport)
    assert model.decide({'stage':'snapshot','required_next_tool':'get_public_snapshot','next_plan_mode':None},['get_public_snapshot']).tool=='get_public_snapshot'
    wire=json.dumps(captured);assert 'required_next_tool' not in wire and 'never-log-this' not in wire
    assert model.last_usage['input_tokens']==10
    model.transport=lambda b:{'choices':[{'message':{'content':'{"tool":"execute","start":"12:00"}'}}]}
    with pytest.raises(BoundaryError):model.decide({},[])


def test_api_missing_config_and_untrusted_endpoint(monkeypatch):
    for key in ('SUPERVISOR_ENDPOINT','SUPERVISOR_MODEL','SUPERVISOR_API_KEY'):monkeypatch.delenv(key,raising=False)
    with pytest.raises(ServiceUnavailable):APISupervisorModel(configuration())
    monkeypatch.setenv('SUPERVISOR_ENDPOINT','http://remote.example/api');monkeypatch.setenv('SUPERVISOR_MODEL','test')
    with pytest.raises(BoundaryError):APISupervisorModel(configuration())


@pytest.mark.parametrize('n',[float('nan'),float('inf'),-1,True])
def test_invalid_critical_numbers_rejected(n):
    with pytest.raises(BoundaryError):number(n)


def test_false_pass_and_incomplete_checker_rejected():
    with pytest.raises(BoundaryError):VerificationSummary('p','r','PASS',True,True,100,100,7001,(0,10),()).validate()
    with pytest.raises(BoundaryError):CheckSummary('p','r','c',True,(('independent_gate',True),)).validate()


@pytest.mark.parametrize('changes',[{'model_version':'other_model'},{'schema_sha256':'b'*64}])
def test_valid_shape_but_wrong_frozen_version_fails_closed(changes):
    class Backend(ScriptedBackend):
        def call(self,tool,args):
            r=super().call(tool,args)
            return replace(r,**changes) if tool=='request_predictions' else r
    s,p=episode(backend=Backend(case()));assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
    assert s.last_audit.metrics['optimizer_calls']==0


def test_service_exception_cannot_smuggle_hidden_values():
    class Backend(ScriptedBackend):
        def call(self,tool,args):raise BoundaryError('latent_wear=0.981 future failure tomorrow')
    s,p=episode(backend=Backend(case()))
    assert '0.981' not in json.dumps(p.to_dict())


def test_used_config_provenance_matches_actual_override():
    c=configuration();c['maximum_replan_attempts']=1
    s,p=episode(config=c)
    assert next(r for r in p.provenance if r.tool=='supervisor_config').response_sha256==digest(c)


def test_unchanged_rejected_candidate_escalates_without_replay():
    class Same(ScriptedBackend):
        def call(self,tool,args):
            r=super().call(tool,args)
            if tool=='solve_robust_schedule':
                self.current_plan=replace(r,schedule_id='unchanged');return self.current_plan
            return r
    s,p=episode('persistent_replay_failure',backend=Same(case('persistent_replay_failure')))
    assert p.outcome=='NO_VERIFIED_RECOMMENDATION'
    assert s.last_audit.metrics['optimizer_calls']==2 and s.last_audit.metrics['replay_calls']==1
    assert 'unchanged rejected candidate' in p.recommendation


def test_no_executor_or_filesystem_capability_in_registry():
    from energy_copilot.supervisor.registry import ARGUMENTS,RESPONSES
    assert 'execute_approved_simulation' not in RESPONSES
    assert not any(set(args)&{'path','schedule','constraints','threshold','seed'} for args in ARGUMENTS.values())


def test_future_mutation_cannot_change_public_snapshot():
    from energy_copilot.robust.state_update import public_snapshot
    import pandas as pd
    from types import SimpleNamespace
    # Frozen public posting-time projection is reused by the new gateway.
    r=pd.DataFrame({'timestamp':pd.to_datetime(['2026-01-18T23:30','2026-01-19T00:00']),
        'asset_id':['MAIN','MAIN'],'kW':[400.,900.]})
    h=pd.DataFrame({'end':pd.to_datetime(['2026-01-18T23:45','2026-01-19T01:00']),
        'start':pd.to_datetime(['2026-01-18T22:00','2026-01-19T00:00']),'heat_id':['old','future']})
    p=pd.DataFrame({'timestamp':pd.to_datetime(['2026-01-18T23:30','2026-01-19T00:00'])})
    from energy_copilot.schema import ALLOWED_OBS_FEATURES
    for name in (*ALLOWED_OBS_FEATURES,'sensor_glitch','measurement_status'):
        if name not in r:r[name]=0.
    for name in ('asset_id','charge_t','liquid_t','billet_t','kWh','kWh_per_t','tap_temp_C','chem_ok'):
        h[name]='IF_01' if name=='asset_id' else 1.
    p['date']=['2026-01-18','2026-01-19'];p['shift']=[2,0]
    sim=SimpleNamespace(readings=r,heats=h,production=p)
    before=public_snapshot(sim,pd.Timestamp('2026-01-19'))
    sim.readings.loc[1,'kW']=123456.;sim.heats.loc[1,'heat_id']='secret altered future'
    after=public_snapshot(sim,pd.Timestamp('2026-01-19'))
    for a,b in zip(before,after):pd.testing.assert_frame_equal(a,b)
