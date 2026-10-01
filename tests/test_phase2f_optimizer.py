"""Maintenance MILP/checker gates with frozen typed prediction coefficients."""
from dataclasses import replace
from pathlib import Path
import json
import pandas as pd
import pytest

from energy_copilot.optimization.contracts import input_from_dict
from energy_copilot.robust import ReservePolicy,DurationScenario
from energy_copilot.robust.state_update import public_snapshot,update_state,remaining_input
from energy_copilot.sim import simulate
from energy_copilot.common import load_config,values
from energy_copilot.forecast import PredictionService
from energy_copilot.maintenance.optimizer import optimize_maintenance,check_plan,candidates


@pytest.fixture(scope='module')
def inp():
    base=input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text()))
    cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    baseline=simulate(cfg,seed=2001,days=8)
    snapshot=public_snapshot(baseline,base.forecast_origin)
    state=update_state(None,base.forecast_origin,snapshot[1],[],[],base)
    current,_=remaining_input(base,state,snapshot,values(cfg),PredictionService('models/phase2b_v1'),grid=1)
    risk=tuple(replace(p,failure_probability=.99,calibrated_probability=.99) for p in current.health_predictions)
    return replace(current,health_predictions=risk)


@pytest.fixture(scope='module')
def plan(inp):
    return optimize_maintenance(inp,ReservePolicy(5),
        (DurationScenario('central'),DurationScenario('upper',use_upper_quantiles=True)),
        {'MILL_01':False,'PMP_01':True})


def test_service_is_movable_and_independently_checked(inp,plan):
    assert plan.plan.releasable,plan.plan.reason
    assert plan.checker['feasible']
    assert plan.candidates and all(a.asset_id=='PMP_01' for a in plan.candidates)
    assert len(plan.actions)==1
    for action in plan.actions:
        for row in plan.plan.schedule:
            assert not(pd.Timestamp(row['start'])<pd.Timestamp(action.end_time) and
                       pd.Timestamp(row['predicted_end'])>pd.Timestamp(action.start_time))
        for row in plan.plan.load_trajectory:
            if pd.Timestamp(action.start_time)<=pd.Timestamp(row['interval_start'])<pd.Timestamp(action.end_time):
                assert row['asset_run']['PMP_01']==0 and row['furnace_on']==0


def test_same_public_state_recommends_same_window(inp,plan):
    again=optimize_maintenance(inp,ReservePolicy(5),
        (DurationScenario('central'),DurationScenario('upper',use_upper_quantiles=True)),
        {'MILL_01':False,'PMP_01':True})
    assert plan.actions==again.actions
    assert plan.plan.schedule==again.plan.schedule
    assert plan.plan.predicted_metrics==again.plan.predicted_metrics


def test_checker_rejects_unmodeled_service_overlap(inp,plan):
    assert plan.actions
    first=plan.plan.schedule[0]
    unsafe=replace(plan.actions[0],start_time=first['start'])
    # An unsupported start or intersection must fail closed, never be released.
    try:
        result=check_plan(inp,plan.plan,(unsafe,),ReservePolicy(5),(DurationScenario('central'),))
    except ValueError:
        return
    assert not result['feasible']


def test_unsafe_health_fallback_rejected(inp):
    bad=replace(inp,health_predictions=(replace(inp.health_predictions[0],status='fallback',usable_for_constraints=False),inp.health_predictions[1]))
    with pytest.raises(ValueError):bad.validate()


def test_candidate_service_cannot_be_moved_into_past(inp):
    now=pd.Timestamp(inp.forecast_origin)+pd.Timedelta(hours=8,minutes=5)
    later=replace(inp,decision_time=now.isoformat())
    windows=candidates(later,{'MILL_01':True,'PMP_01':True})
    assert windows and all(pd.Timestamp(a.start_time)>=now for a in windows)
    assert not any(pd.Timestamp(a.start_time).hour in (0,4,8) for a in windows)
