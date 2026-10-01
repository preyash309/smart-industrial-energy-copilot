from dataclasses import replace
import pytest
from energy_copilot.optimization import optimize,check_schedule
from scripts.phase2c import reference_input


@pytest.fixture(scope='module')
def planning_input():return reference_input()[0]


@pytest.fixture(scope='module')
def feasible(planning_input):return optimize(planning_input,practices=('normal',))


def test_c1_reference_gate(feasible):
    assert feasible.releasable,feasible.reason
    assert feasible.checker['feasible'] and feasible.checker['checked_slots']==96
    assert len(feasible.schedule)==13
    assert feasible.predicted_metrics['bars_t']==pytest.approx(118.56)
    assert feasible.predicted_metrics['billets_t']==pytest.approx(123.5)
    assert feasible.predicted_metrics['final_inventory_t']==pytest.approx(50)
    assert feasible.predicted_metrics['predicted_peak_kVA_bound']<=7000


def test_c1_checker_rejects_tampering(planning_input,feasible):
    loads=[dict(r) for r in feasible.load_trajectory];loads[4]['pump_on']=False
    assert not check_schedule(planning_input,replace(feasible,load_trajectory=tuple(loads)))['feasible']
    schedule=[dict(r) for r in feasible.schedule];schedule[1]['start']=schedule[0]['start']
    assert not check_schedule(planning_input,replace(feasible,schedule=tuple(schedule)))['feasible']


def test_strict_15_minute_start_policy_is_explicitly_infeasible(planning_input):
    inp=replace(planning_input,constraints=replace(planning_input.constraints,candidate_step_minutes=15),
                heat_candidates=tuple(k for k in planning_input.heat_candidates if int(k.start[14:16])%15==0))
    result=optimize(inp,practices=('normal',))
    assert result.status=='infeasible' and not result.releasable


def test_c1_reproducible(planning_input,feasible):
    assert optimize(planning_input,practices=('normal',)).to_dict()==feasible.to_dict()
