"""Facade tests run without Streamlit or network; demo never invokes the plant."""
import copy,json,time
from pathlib import Path
import pytest
from energy_copilot.dashboard.contracts import ROOT,DashboardError,validate_bundle,read_json,file_hash
from energy_copilot.dashboard.demo_loader import load_demo
from energy_copilot.dashboard.service import DashboardService
from energy_copilot.dashboard.scenarios import SCENARIOS,PAGES

@pytest.mark.parametrize('key',SCENARIOS)
def test_coherent_scenario(key):
    b=load_demo(key);assert b['metadata']['scenario']==key
    assert b['metadata']['seed']==SCENARIOS[key]['seed'] and b['metadata']['day']==SCENARIOS[key]['day']
    s=DashboardService(key)
    assert s.get_evidence()['packet']['snapshot']['snapshot_id']==b['metadata']['snapshot_id']
    assert s.get_schedule_comparison()['schedule_id']==s.packet['optimizer_plan']['schedule_id']
    assert len(PAGES)==7

@pytest.mark.parametrize('field',['seed','day','snapshot_id','origin'])
def test_mixed_scenario_metadata_rejected(field):
    b=load_demo('normal');b['metadata'][field]=123 if field in ('seed','day') else 'wrong'
    with pytest.raises((DashboardError,ValueError)):validate_bundle(b)

def test_mixed_forecast_and_replay_rejected():
    a=load_demo('normal');b=load_demo('recovery')
    for name in ('predictions','replay_outcome'):
        invalid=copy.deepcopy(a);invalid['packet'][name]=b['packet'][name]
        with pytest.raises(DashboardError):validate_bundle(invalid)

def test_future_current_snapshot_rejected():
    b=load_demo('normal');b['packet']['snapshot']['observations'][0]['available_at']='2099-01-01T00:00:00'
    with pytest.raises(DashboardError):validate_bundle(b)

def test_forged_verified_failure_rejected():
    b=load_demo('rejection');b['packet']['outcome']='VERIFIED_RECOMMENDATION'
    with pytest.raises(DashboardError):validate_bundle(b)

def test_predicted_and_realized_not_swapped():
    s=DashboardService('normal');v=s.get_overview()
    assert v['electricity_kWh']==s.packet['replay_outcome']['realized_energy_kWh']
    assert v['electricity_kWh']!=s.packet['optimizer_plan']['predicted_energy_kWh']
    s=DashboardService('rejection');assert s.get_overview()['label']=='OPTIMIZER-PREDICTED · UNVERIFIED'
    assert s.get_overview()['production_label']=='Production target'

def test_rejected_candidate_remains_visible_not_substituted_by_recovery():
    a=DashboardService('rejection');d=DashboardService('recovery')
    assert a.packet['optimizer_plan']['optimizer_feasible'] and not a.packet['replay_outcome']['physically_valid']
    assert a.packet['outcome']=='NO_VERIFIED_RECOMMENDATION'
    assert a.packet['optimizer_plan']['schedule_id']==d.packet['alternatives_considered'][0]['schedule_id']
    assert a.packet['optimizer_plan']['schedule_id']!=d.packet['optimizer_plan']['schedule_id']
    assert a.bundle['heat_analytics']==[] and a.bundle['replay_observations']==[]

def test_failure_does_not_borrow_meter_data():
    s=DashboardService('maintenance');assert not s.bundle['replay_observations']
    assert s.packet['replay_outcome']['realized_energy_kWh'] is None
    assert s.get_maintenance_view()['initial_selected']
    assert not s.get_maintenance_view()['verified']

@pytest.mark.parametrize('key',['maintenance','rejection'])
def test_unverified_approval_denied(key,tmp_path):
    s=DashboardService(key,runtime_root=tmp_path)
    with pytest.raises(DashboardError):s.approve_decision(True)
    assert s.status=='PROPOSED'

def test_approval_confirmed_audited_immutable_packet(tmp_path):
    s=DashboardService('normal',runtime_root=tmp_path);before=copy.deepcopy(s.packet)
    with pytest.raises(DashboardError):s.approve_decision(False)
    assert s.status=='VERIFIED';assert s.approve_decision(True,'Operator reviewed all gates')=='APPROVED'
    assert s.packet==before and s.packet['disposition']=='VERIFIED'
    audit=read_json_lines(s._directory/'audit.jsonl')
    assert audit[-1]['kind']=='operator_feedback' and audit[-1]['payload']['explicit_simulated_approval']
    assert not s._approval.enabled
    with pytest.raises(DashboardError):s.reject_decision()

def read_json_lines(path):return [json.loads(x) for x in path.read_text().splitlines()]

def test_reject_and_defer_semantics(tmp_path):
    s=DashboardService('recovery',runtime_root=tmp_path)
    assert s.defer_decision('Review later')=='VERIFIED' and s.last_feedback=='defer'
    assert s.reject_decision('Not accepted by operator')=='REJECTED'
    with pytest.raises(DashboardError):s.approve_decision(True)
    assert any(r['kind']=='operator_feedback' and r['payload']['feedback']['action']=='defer' for r in read_json_lines(s._directory/'audit.jsonl'))

def test_rejected_unverified_review_cannot_promote(tmp_path):
    s=DashboardService('rejection',runtime_root=tmp_path)
    assert s.defer_decision()=='PROPOSED'
    assert s.reject_decision()=='REJECTED'
    with pytest.raises(DashboardError):s.approve_decision(True)

def test_sessions_and_reset_isolated(tmp_path):
    a=DashboardService('normal',runtime_root=tmp_path);b=DashboardService('normal',runtime_root=tmp_path)
    a.approve_decision(True);assert b.status=='VERIFIED'
    reset=DashboardService('normal',runtime_root=tmp_path);assert reset.status=='VERIFIED'
    assert a._directory.exists() and a._directory!=reset._directory

def test_demo_never_loads_live_stack(monkeypatch):
    import sys
    # The facade is deliberately not importing StackBackend or a simulator.
    monkeypatch.setitem(sys.modules,'energy_copilot.supervisor.stack_backend',None)
    monkeypatch.setitem(sys.modules,'energy_copilot.dashboard.live_runner',None)
    for key in SCENARIOS:
        s=DashboardService(key);s.get_overview();s.get_energy_view();s.get_schedule_comparison();s.get_impact_summary()

def test_historical_claims_are_exact_frozen_fields():
    rows=read_json(ROOT/'dashboard_deck_metrics.json')['metrics']
    for r in rows:
        source=ROOT/r['source_artifact'];assert file_hash(source)==r['source_sha256']
        value=read_json(source)
        for part in r['source_field'].split('.'):value=value[part]
        assert value==r['value']
        assert r['evidence_label'] and r['scenario'] and r['unit'] and r['caveat']
    assert not any('AI4I' in r['scenario'] or 'UCI' in r['scenario'] for r in rows)

def test_missing_artifact_sanitized(tmp_path):
    with pytest.raises(DashboardError,match='Evidence is unavailable'):read_json(tmp_path/'missing.json')

def test_no_hidden_fields_in_operational_bundle():
    for key in SCENARIOS:
        b=load_demo(key)
        def walk(node):
            if isinstance(node,dict):
                assert not any(any(t in k.lower() for t in ('latent','wear','future_fault','repair_tape')) for k in node)
                for v in node.values():walk(v)
            elif isinstance(node,list):
                for v in node:walk(v)
        walk(b)

def test_live_worker_calls_actual_frozen_backend():
    # No precomputed packet path in the live worker; integration is also exercised by the release run.
    text=(ROOT/'scripts/phase3a_live.py').read_text()
    assert 'StackBackend.fresh_scenario' in text and 'Supervisor(ProgressFacade(),RuleBasedModel())' in text
    assert 'load_demo' not in text and 'APISupervisorModel' not in text

def test_navigation_facade_performance():
    s=DashboardService('normal');start=time.perf_counter()
    for _ in range(10):s.get_overview();s.get_energy_view();s.get_schedule_comparison();s.get_maintenance_view();s.get_decision_packet()
    assert (time.perf_counter()-start)/10<1.0

@pytest.mark.parametrize('section,field',[('snapshot','last_posted_at'),('predictions','available_at')])
def test_stale_evidence_fails_closed(section,field):
    from datetime import datetime,timedelta
    b=load_demo('normal');origin=datetime.fromisoformat(b['metadata']['origin'])
    b['packet'][section][field]=(origin-timedelta(hours=1)).isoformat()
    with pytest.raises(DashboardError,match='Stale'):validate_bundle(b)

def test_failed_component_check_cannot_be_verified():
    b=load_demo('normal');b['packet']['independent_check']['checks'][0][1]=False
    with pytest.raises(DashboardError,match='Unverified'):validate_bundle(b)

def test_incomplete_production_cannot_be_verified():
    b=load_demo('normal');b['packet']['replay_outcome']['production_complete']=False
    with pytest.raises(DashboardError,match='Unverified'):validate_bundle(b)

def test_live_review_audit_not_labelled_as_demo(tmp_path):
    b=load_demo('normal');b['metadata']['scope']='LIVE DETERMINISTIC SIMULATION · COMPLETED'
    s=DashboardService(bundle=b,runtime_root=tmp_path);s.defer_decision()
    audit=read_json_lines(s._directory/'audit.jsonl')
    assert next(r['payload']['mode'] for r in audit if r['kind']=='dashboard_session')=='LIVE-OPERATOR-REVIEW'
