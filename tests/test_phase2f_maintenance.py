"""Phase II-F synthetic service, information and accounting boundaries."""
from dataclasses import replace
from pathlib import Path
import json
import pandas as pd
import pytest

from energy_copilot.common import load_config,values,canonical_hash
from energy_copilot.forecast.interfaces import HealthPrediction
from energy_copilot.maintenance.contracts import MaintenanceAction,validate_actions,settings
from energy_copilot.maintenance.scenario import scenario
from energy_copilot.maintenance.execution import simulate
from energy_copilot.maintenance.independent_accounting import independent
from energy_copilot.maintenance.policy import MaintenancePolicy,eligible_assets
from energy_copilot.maintenance.evaluation import attribute_service
from energy_copilot.robust.execution_prefix import simulate as frozen_prefix
from energy_copilot.replay.origin_state import frame_hash
from scripts.phase2f import split,guard


@pytest.fixture(scope='module')
def cfg():return load_config('data/processed/sim_v1.1/config_snapshot.yaml')


def test_frozen_upstream_and_seed_firewall():
    assert guard()>3000
    s=split()
    assert not (set(s['development'])|set(s['validation'])|set(s['final']))&set(range(201,211))
    assert set(s['development']).isdisjoint(s['validation'])
    assert set(s['validation']).isdisjoint(s['final'])


def test_no_action_byte_equivalence(cfg):
    old=frozen_prefix(cfg,seed=2001,days=2);new=simulate(cfg,seed=2001,days=2)
    for name in ('readings','heats','production','events','latent_truth','latent_heats'):
        assert frame_hash(getattr(old,name))==frame_hash(getattr(new,name))
    assert old.summary==new.summary and old.scenario_manifest==new.scenario_manifest


def test_service_changes_only_affected_wear_tape(cfg):
    action=MaintenanceAction('MILL_01','2026-01-05T20:00:00',15)
    base=scenario(values(cfg),2001,2)
    a=scenario(values(cfg),2001,2,(action,));b=scenario(values(cfg),2001,2,(action,))
    assert canonical_hash(a)==canonical_hash(b)
    assert a['original_exogenous_sha256']==base['hash']
    assert a['wear']['PMP_01'].tolist()==base['wear']['PMP_01'].tolist()
    assert a['repairs']['PMP_01']==base['repairs']['PMP_01']
    for key in base:
        if key not in ('hash','wear','repairs','events'):
            assert canonical_hash(a[key])==canonical_hash(base[key]),key
    assert a['events']!=base['events']
    assert len([e for e in a['events'] if e['type']=='preventive_service'])==1
    assert len([e for e in a['events'] if e['type']=='failure' and e['asset_id']=='MILL_01'])<=len([e for e in base['events'] if e['type']=='failure' and e['asset_id']=='MILL_01'])


def test_synthetic_service_physical_accounting(cfg):
    action=MaintenanceAction('MILL_01','2026-01-05T20:00:00',15)
    sim=simulate(cfg,seed=2001,days=2,maintenance_actions=(action,))
    tables={n:getattr(sim,n) for n in ('latent_truth','latent_heats','events','production')}
    _,checks,_=independent(tables,sim.config)
    assert sum(checks.values())==0
    row=sim.latent_truth[(sim.latent_truth.asset_id=='MILL_01')&(sim.latent_truth.timestamp==pd.Timestamp(action.start_time))].iloc[0]
    assert row.kW==0 and row.state.startswith('preventive_service')
    assert sim.scenario_manifest['exogenous_scenario_sha256']==scenario(values(cfg),2001,2)['hash']


def test_service_replay_determinism_and_pump_interlock(cfg):
    action=MaintenanceAction('MILL_01','2026-01-05T20:00:00',15)
    first=simulate(cfg,seed=2001,days=2,maintenance_actions=(action,))
    again=simulate(cfg,seed=2001,days=2,maintenance_actions=(action,))
    for name in ('readings','heats','production','events','latent_truth','latent_heats'):
        assert frame_hash(getattr(first,name))==frame_hash(getattr(again,name))
    assert first.summary==again.summary and first.scenario_manifest==again.scenario_manifest
    pump=MaintenanceAction('PMP_01','2026-01-05T00:00:00',15)
    with pytest.raises(ValueError,match='Pump maintenance overlaps an induction heat'):
        simulate(cfg,seed=2001,days=2,maintenance_actions=(pump,))


def test_mill_service_blocks_rolling_without_changing_if(cfg):
    action=MaintenanceAction('MILL_01','2026-01-05T08:00:00',15)
    sim=simulate(cfg,seed=2001,days=2,maintenance_actions=(action,))
    at=pd.Timestamp(action.start_time)
    site=sim.latent_truth[(sim.latent_truth.asset_id=='MAIN')&sim.latent_truth.timestamp.eq(at)].iloc[0]
    mill=sim.latent_truth[(sim.latent_truth.asset_id=='MILL_01')&sim.latent_truth.timestamp.eq(at)].iloc[0]
    assert site.rolled_billet_t==0 and site.mill_available_min==0
    assert mill.kW==0 and mill.state.startswith('preventive_service')
    assert site.if_powered_min>0


def test_action_contract_rejects_fictional_or_overlapping():
    c=settings();origin='2026-01-05T00:00:00'
    valid=MaintenanceAction('PMP_01','2026-01-05T04:00:00',15)
    assert valid.validate(c,origin,2)==valid
    with pytest.raises(ValueError):replace(valid,asset_id='IF_01').validate(c,origin,2)
    with pytest.raises(ValueError):replace(valid,start_time='2026-01-05T04:05:00').validate(c,origin,2)
    with pytest.raises(ValueError):replace(valid,duration_min=30).validate(c,origin,2)
    with pytest.raises(ValueError):validate_actions((valid,valid),c,origin,2)


def test_policy_only_consumes_closed_observations():
    now=pd.Timestamp('2026-01-05T01:00:00')
    rows=[]
    for asset in ('MILL_01','PMP_01'):
        for minute in (0,15,30,45,60):
            rows.append(dict(asset_id=asset,timestamp=pd.Timestamp('2026-01-05')+pd.Timedelta(minutes=minute),
                             vibration_mm_s=2.0 if minute<60 else 999.,temp_C=65.,state='on',sensor_glitch=False))
    public=pd.DataFrame(rows)
    preds=tuple(HealthPrediction(asset,24,.9,.9,now.isoformat(),'health_v1','model',True) for asset in ('MILL_01','PMP_01'))
    eligible,audit=eligible_assets(preds,public,now,MaintenancePolicy(.7,.7,1))
    assert eligible=={'MILL_01':True,'PMP_01':True}
    assert all(r['visible_evidence']['vibration_mm_s']==2.0 for r in audit)
    with pytest.raises(ValueError):eligible_assets((replace(preds[0],available_at=(now+pd.Timedelta(minutes=1)).isoformat()),preds[1]),public,now,MaintenancePolicy(.7,.7,1))
    with pytest.raises(ValueError):eligible_assets((replace(preds[0],status='fallback'),preds[1]),public,now,MaintenancePolicy(.7,.7,1))


def test_health_persistence_uses_prior_public_risk():
    now=pd.Timestamp('2026-01-05T01:00:00')
    public=pd.DataFrame([dict(asset_id=a,timestamp=now-pd.Timedelta(minutes=m),vibration_mm_s=2.,temp_C=65.,state='on',sensor_glitch=False)
                         for a in ('MILL_01','PMP_01') for m in (15,30,45,60)])
    p=tuple(HealthPrediction(a,24,.9,.9,now.isoformat(),'health_v1','model',True) for a in ('MILL_01','PMP_01'))
    policy=MaintenancePolicy(.7,.7,2)
    first,_=eligible_assets(p,public,now,policy)
    assert first=={'MILL_01':False,'PMP_01':False}
    past=[dict(asset_id=a,available_at=(now-pd.Timedelta(hours=1)).isoformat(),eligible_probability=.9,recent_valid_fraction=1.,recent_state='on') for a in first]
    second,_=eligible_assets(p,public,now,policy,past)
    assert second=={'MILL_01':True,'PMP_01':True}


def test_false_service_and_avoided_failure_retained():
    from types import SimpleNamespace
    actions=(MaintenanceAction('MILL_01','2026-01-19T08:00:00',15),
             MaintenanceAction('PMP_01','2026-01-19T08:00:00',15))
    no_service=SimpleNamespace(events=pd.DataFrame([
        dict(asset_id='PMP_01',type='failure',start=pd.Timestamp('2026-01-19T10:00:00'))]))
    maintained=SimpleNamespace(events=pd.DataFrame(columns=['asset_id','type','start']))
    rows=attribute_service(no_service,maintained,actions)
    assert {r['asset_id']:r['classification'] for r in rows}=={
        'MILL_01':'unnecessary_24h','PMP_01':'averted_within_24h'}
    unknown=attribute_service(None,maintained,actions)
    assert len(unknown)==2 and all(r['classification']=='undetermined_counterfactual' for r in unknown)


def test_synthetic_wear_reset_causally_removes_matched_pump_failure(cfg):
    c=values(cfg);base=scenario(c,2001,30)
    action=MaintenanceAction('PMP_01','2026-01-19T00:00:00',15)
    successor=scenario(c,2001,30,(action,))
    lo,hi=14*1440,15*1440
    failures=lambda tape:[e for e in tape['events'] if e['asset_id']=='PMP_01' and e['type']=='failure' and lo<=e['start_min']<hi]
    assert len(failures(base))==1 and len(failures(successor))==0
    assert successor['original_exogenous_sha256']==base['hash']


def test_planner_modules_cannot_directly_read_hidden_tables():
    import ast,inspect
    from energy_copilot.maintenance import controller,optimizer,policy
    forbidden={'latent_truth','latent_heats','events','fault_label','wear','repairs'}
    for module in (controller,optimizer,policy):
        tree=ast.parse(inspect.getsource(module))
        accessed={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
        assert not accessed&forbidden,(module.__name__,accessed&forbidden)


def test_future_outcomes_and_hidden_tables_cannot_change_public_snapshot(cfg):
    from energy_copilot.robust.state_update import public_snapshot
    sim=simulate(cfg,seed=2001,days=2)
    now=pd.Timestamp('2026-01-05T08:00:00')
    expected=public_snapshot(sim,now)
    class OracleTrap:
        def __init__(self):
            self.readings=sim.readings.copy(deep=True)
            self.heats=sim.heats.copy(deep=True)
            self.production=sim.production.copy(deep=True)
        @property
        def events(self):raise AssertionError('Future events are forbidden')
        @property
        def latent_truth(self):raise AssertionError('Hidden truth is forbidden')
        @property
        def latent_heats(self):raise AssertionError('Hidden heat outcomes are forbidden')
    changed=OracleTrap()
    future=changed.readings.timestamp+pd.Timedelta(minutes=15)>now
    changed.readings.loc[future,'kW']=999999.
    changed.readings.loc[future,'vibration_mm_s']=999999.
    changed.heats.loc[changed.heats.end>now,'kWh']=999999.
    actual=public_snapshot(changed,now)
    for before,after in zip(expected,actual):pd.testing.assert_frame_equal(before,after)


def test_completed_service_is_immutable_and_not_future():
    from dataclasses import FrozenInstanceError
    from energy_copilot.maintenance.contracts import ExecutedMaintenance
    record=ExecutedMaintenance('PMP_01','2026-01-05T04:00:00','2026-01-05T04:15:00',
                               'preventive_replacement','reset_wear')
    assert record.validate('2026-01-05T04:15:00',settings(),'2026-01-05T00:00:00',2)==record
    with pytest.raises(ValueError,match='Uncompleted'):
        record.validate('2026-01-05T04:10:00',settings(),'2026-01-05T00:00:00',2)
    with pytest.raises(FrozenInstanceError):record.start_time='2026-01-05T08:00:00'
