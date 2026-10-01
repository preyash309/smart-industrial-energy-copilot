"""Phase II-E adversarial gates, isolated from all frozen test/source files."""
from pathlib import Path
from dataclasses import replace,asdict
from types import SimpleNamespace
import copy,json
import pandas as pd
import pytest
from energy_copilot.common import load_config,values,canonical_hash
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization import optimize
from energy_copilot.optimization.contracts import input_from_dict
from energy_copilot.robust import ReservePolicy,DurationScenario,optimize_robust
from energy_copilot.robust.checker import check_robust
from energy_copilot.robust.scenarios import scenario_coefficients,make_scenarios
from energy_copilot.robust.integrity import validate_split,require_development,verify_upstream
from energy_copilot.robust.state_update import public_snapshot,update_state,remaining_input
from energy_copilot.robust.execution_prefix import simulate as prefix_simulate
from energy_copilot.replay.compatible_v111 import simulate
from energy_copilot.replay.origin_state import frame_hash


@pytest.fixture(scope='module')
def inp():return input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))


@pytest.fixture(scope='module')
def reserve_plan(inp):return optimize_robust(inp,ReservePolicy(10,0))


@pytest.fixture(scope='module')
def cfg():return load_config('data/processed/sim_v1.1/config_snapshot.yaml')


@pytest.fixture(scope='module')
def prefix(cfg):return prefix_simulate(cfg,heat_limits={7:1,**{d:0 for d in range(8,30)}},practice_by_day={7:40},seed=1001,days=30)


def test_reserve_is_hard(inp,reserve_plan):
    assert reserve_plan.plan.releasable
    end=pd.Timestamp(reserve_plan.plan.schedule[-1]['predicted_end'])
    assert end<=pd.Timestamp(inp.forecast_origin)+pd.Timedelta(minutes=1430)
    assert check_robust(inp,reserve_plan.plan,ReservePolicy(10),())['feasible']
    assert not check_robust(inp,reserve_plan.plan,ReservePolicy(100),())['feasible']


def test_buffer_is_hard(inp):
    policy=ReservePolicy(5,0,1);r=optimize_robust(inp,policy)
    assert r.plan.releasable
    for a,b in zip(r.plan.schedule,r.plan.schedule[1:]):
        assert pd.Timestamp(b['start'])>=pd.Timestamp(a['reserved_end'])+pd.Timedelta(minutes=1)
    assert not optimize_robust(inp,ReservePolicy(0,0,20)).plan.releasable


def test_robust_scenarios_all_checked(inp):
    scenarios=(DurationScenario('central'),DurationScenario('upper',use_upper_quantiles=True))
    r=optimize_robust(inp,ReservePolicy(),scenarios)
    assert r.plan.releasable
    assert len(r.checker['scenario_checks'])==2
    assert all(s['feasible'] for s in r.checker['scenario_checks'])


def test_severe_scenario_explicit_infeasible(inp):
    r=optimize_robust(inp,ReservePolicy(),(DurationScenario('impossible_test',tuple([30]*13)),))
    assert r.plan.status=='infeasible' and not r.plan.releasable


def test_uncertainty_not_double_counted(inp):
    k=next(k for k in inp.heat_candidates if k.prediction.practice_mode=='practice_loss_40')
    s=DurationScenario('r',tuple([2]*13),use_upper_quantiles=True)
    _,d=scenario_coefficients(k,inp,s,0)
    assert d==max(k.prediction.duration_p90_min,k.prediction.duration_p50_min+2,
                  k.prediction.energy_p90_kWh/5000*60+27)


def test_whole_day_vectors_and_no_oracle():
    c={'selected_day_residual_vectors':[list(range(13)),list(range(13,26))],'positive_residual_p95_min':9}
    s=make_scenarios(c,['D007_H05','D007_H06'])
    assert s[2].residual_min==(5,6) and s[3].residual_min==(18,19)
    assert s[-1].residual_min==(9,0)


@pytest.mark.parametrize('bad',['negative','nan','infinity'])
def test_policy_rejects_invalid(bad):
    v={'negative':-1,'nan':float('nan'),'infinity':float('inf')}[bad]
    with pytest.raises(ValueError):ReservePolicy(v).validate()


def test_reproducible_solve(inp,reserve_plan):
    assert canonical_hash(reserve_plan.to_dict())==canonical_hash(optimize_robust(inp,ReservePolicy(10,0)).to_dict())


def test_production_not_sacrificed(inp,reserve_plan):
    assert reserve_plan.plan.predicted_metrics['bars_t']==pytest.approx(inp.production_order.bars_t)
    assert reserve_plan.plan.predicted_metrics['predicted_total_kWh']>0
    assert reserve_plan.plan.predicted_metrics['predicted_tariff_cost_Rs']>0


def test_split_firewall():
    split=json.loads(Path('configs/robustness_split_v1.json').read_text());assert validate_split(split)
    for seed in range(201,211):
        with pytest.raises(ValueError):require_development(seed,split)
    s=copy.deepcopy(split);s['development'].append(201)
    with pytest.raises(ValueError):validate_split(s)


def test_frozen_upstream_unchanged():assert verify_upstream()['status']=='PASS'


def test_prefix_default_equivalence(cfg):
    a=simulate(cfg,seed=1001,days=30);b=prefix_simulate(cfg,seed=1001,days=30)
    for name in ('readings','heats','production','events','latent_truth','latent_heats'):
        assert frame_hash(getattr(a,name))==frame_hash(getattr(b,name))
    assert a.summary==b.summary and a.scenario_manifest==b.scenario_manifest


def test_prefix_matches_full_posted_truth(cfg,prefix):
    full=simulate(cfg,practice_by_day={7:40},seed=1001,days=30)
    at=prefix.heats[prefix.heats.heat_id.eq('D007_H00')].end.iloc[0].ceil('15min')
    a=public_snapshot(full,at);b=public_snapshot(prefix,at)
    for x,y in zip(a,b):assert frame_hash(x)==frame_hash(y)
    assert prefix.summary['releasable'] is False


def test_snapshot_projects_hidden_labels_and_future(prefix):
    at=pd.Timestamp('2026-01-12T00:00:00');r,h,p=public_snapshot(prefix,at)
    assert (r.timestamp+pd.Timedelta(minutes=15)<=at).all() and (h.end<=at).all()
    assert 'fault_label' not in h
    assert not any('latent' in col or 'failure' in col for col in list(r)+list(h)+list(p))
    class PublicOnly:
        readings=prefix.readings;heats=prefix.heats;production=prefix.production
        @property
        def events(self):raise AssertionError('Events forbidden')
        @property
        def latent_truth(self):raise AssertionError('Truth forbidden')
    assert len(public_snapshot(PublicOnly(),at)[0])==len(r)


@pytest.fixture(scope='module')
def state(inp,prefix):
    at=prefix.heats[prefix.heats.heat_id.eq('D007_H00')].end.iloc[0].ceil('15min')
    _,h,_=public_snapshot(prefix,at);one=h[h.heat_id.eq('D007_H00')].iloc[0]
    feed=[2.0]*int((at-pd.Timestamp(inp.forecast_origin)).total_seconds()/900)
    executed=[dict(heat_id='D007_H00',start=one.start.isoformat(),end=one.end.isoformat())]
    return update_state(None,at,h,feed,executed,inp)


def test_inventory_update_from_public_acknowledgements(inp,state):
    assert state.actual_inventory_t==pytest.approx(inp.initial_inventory_t+9.5-sum(state.executed_rolling))
    assert state.completed_heats==('D007_H00',) and len(state.remaining_heats)==12


def test_executed_decisions_immutable(inp,prefix,state):
    at=pd.Timestamp(state.current_time)+pd.Timedelta(minutes=15);_,h,_=public_snapshot(prefix,at)
    with pytest.raises(ValueError):update_state(state,at,h,list(state.executed_rolling)+[0],[],inp)
    with pytest.raises(ValueError):update_state(state,state.current_time,h,state.executed_rolling,state.frozen_executed_decisions,inp)
    if state.executed_rolling:
        feed=list(state.executed_rolling)+[0];feed[0]=1
        with pytest.raises(ValueError):update_state(state,at,h,feed,state.frozen_executed_decisions,inp)


@pytest.fixture(scope='module')
def remaining(inp,state,prefix,cfg):
    return remaining_input(inp,state,public_snapshot(prefix,state.current_time),values(cfg),PredictionService('models/phase2b_v1'))[0]


def test_legitimate_intraday_contract(remaining,state,inp):
    assert remaining.forecast_origin==state.current_time
    assert all(pd.Timestamp(k.start)>=pd.Timestamp(state.current_time) for k in remaining.heat_candidates)
    assert all(pd.Timestamp(k.prediction.available_at)<=pd.Timestamp(state.current_time) for k in remaining.heat_candidates)
    assert all(k.heat_id!='D007_H00' for k in remaining.heat_candidates)
    assert remaining.background_load_forecast[-1]==inp.background_load_forecast[-1]
    assert remaining.background_load_forecast[0].available_at==inp.forecast_origin


def test_future_prediction_rejected(remaining):
    k=remaining.heat_candidates[0];bad=replace(k,prediction=replace(k.prediction,available_at='2026-01-13T00:00:00'))
    with pytest.raises(ValueError):replace(remaining,heat_candidates=(bad,)+remaining.heat_candidates[1:]).validate()


def test_replan_deterministic_and_targets(remaining):
    a=optimize_robust(remaining);b=optimize_robust(remaining)
    assert a.plan.releasable and a.to_dict()==b.to_dict()
    assert a.plan.predicted_metrics['bars_t']==pytest.approx(remaining.production_order.bars_t)


def test_physical_bounds_cannot_change(remaining):
    with pytest.raises(ValueError):replace(remaining,constraints=replace(remaining.constraints,demand_limit_kVA=8000)).validate()


@pytest.fixture(scope='module')
def immediate(inp,prefix,cfg):
    one=prefix.heats[prefix.heats.heat_id.eq('D007_H00')].iloc[0];at=one.end
    snapshot=public_snapshot(prefix,at)
    import math
    feed=[2.0]*math.ceil((at-pd.Timestamp(inp.forecast_origin)).total_seconds()/900)
    executed=[dict(heat_id=one.heat_id,start=one.start.isoformat(),end=one.end.isoformat())]
    state=update_state(None,at,snapshot[1],feed,executed,inp)
    planning,provenance=remaining_input(inp,state,snapshot,values(cfg),PredictionService('models/phase2b_v1'),grid=1)
    return state,planning,provenance,snapshot


def test_immediate_completion_does_not_publish_open_interval(immediate):
    state,planning,provenance,snapshot=immediate
    assert pd.Timestamp(planning.forecast_origin)<pd.Timestamp(state.current_time)
    assert planning.decision_time==state.current_time
    assert (snapshot[0].timestamp+pd.Timedelta(minutes=15)<=pd.Timestamp(state.current_time)).all()
    assert all(pd.Timestamp(k.prediction.available_at)<=pd.Timestamp(state.current_time) for k in planning.heat_candidates)
    assert all(pd.Timestamp(k.start)>=pd.Timestamp(state.current_time) for k in planning.heat_candidates)


def test_partial_slot_material_acknowledgements(immediate):
    state,planning,_,_=immediate
    assert planning.known_arrivals[1]==9.5 and planning.committed_first_feed_t==2
    assert planning.initial_inventory_t==pytest.approx(state.actual_inventory_t+2-9.5)


def test_partial_slot_replan_independent_accounting(immediate):
    state,planning,_,_=immediate;r=optimize_robust(planning,ReservePolicy(5))
    assert r.plan.releasable and r.checker['nominal']['mass_residual_t']==pytest.approx(0,abs=1e-6)
    assert r.plan.load_trajectory[0]['rolling_billet_t']==2
    assert r.plan.inventory_trajectory[1]['inventory_t']==pytest.approx(state.actual_inventory_t)
    assert r.plan.predicted_metrics['bars_t']==pytest.approx(planning.production_order.bars_t)


def test_completed_records_are_deeply_immutable(immediate):
    from dataclasses import FrozenInstanceError
    row=immediate[0].frozen_executed_decisions[0]
    with pytest.raises(FrozenInstanceError):row.start='2026-01-12T03:00:00'


def test_target_cannot_be_lowered_in_replan(immediate):
    p=immediate[1]
    with pytest.raises(ValueError):replace(p,production_order=replace(p.production_order,bars_t=0)).validate()


def test_known_future_arrival_forbidden(immediate):
    p=immediate[1];arr=list(p.known_arrivals);arr[3]=9.5
    with pytest.raises(ValueError):replace(p,known_arrivals=tuple(arr)).validate()


def test_hidden_poison_column_not_projected(prefix):
    r=prefix.readings.assign(latent_health=1,future_failure='tomorrow')
    x=public_snapshot(SimpleNamespace(readings=r,heats=prefix.heats,production=prefix.production),'2026-01-12T00:00:00')
    assert 'latent_health' not in x[0] and 'future_failure' not in x[0]
