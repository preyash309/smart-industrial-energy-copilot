from dataclasses import replace
import copy
import pytest
from scripts.phase2c import reference_input
from energy_copilot.optimization import optimize,check_schedule


@pytest.fixture(scope='module')
def inp():return replace(reference_input()[0],objective_mode='cost')


@pytest.fixture(scope='module')
def result(inp):return optimize(inp)


def test_c4_practice_gate(inp,result):
    normal=optimize(inp,practices=('normal',))
    assert result.releasable and normal.releasable
    assert set(r['selected_practice'] for r in result.schedule)=={'practice_loss_40'}
    assert result.predicted_metrics['predicted_tariff_cost_Rs']<=normal.predicted_metrics['predicted_tariff_cost_Rs']+1e-6
    assert result.predicted_metrics['predicted_IF_SEC_kWh_per_t']<normal.predicted_metrics['predicted_IF_SEC_kWh_per_t']


def test_c5_modes(inp,result):
    conservative=replace(inp,optimization_mode='conservative');r=optimize(conservative)
    assert r.releasable and r.checker['feasible']
    for row in r.schedule:
        assert row['selected_duration_min']==row['duration_p90_min']
        assert row['selected_energy_kWh']==row['energy_p90_kWh']
    for row in result.schedule:
        assert row['selected_duration_min']==row['duration_p50_min']
        assert row['selected_energy_kWh']==row['energy_p50_kWh']
    assert r.predicted_metrics['reserved_furnace_utilization']>=result.predicted_metrics['reserved_furnace_utilization']
    for a,b,p in zip(result.load_trajectory,r.load_trajectory,inp.background_load_forecast):
        assert a['asset_kWh']['AUX']==pytest.approx(p.load_p50_kW*.25)
        assert b['asset_kWh']['AUX']==pytest.approx(p.load_p90_kW*.25)


@pytest.mark.parametrize('tamper',['duplicate_heat','overlap','energy','duration','inventory','demand','pump','stock_borrow','rolling_capacity','state','cost','NaN','RHF','production','availability','binding_slack','solver_objective','extra_hidden_field'])
def test_independent_checker_adversarial(inp,result,tamper):
    rows=copy.deepcopy(result.load_trajectory);schedule=copy.deepcopy(result.schedule);inv=copy.deepcopy(result.inventory_trajectory);metrics=copy.deepcopy(result.predicted_metrics)
    if tamper=='duplicate_heat':schedule=(schedule[0],)*len(schedule)
    elif tamper=='overlap':schedule[1]['start']=schedule[0]['start']
    elif tamper=='energy':schedule[0]['selected_energy_kWh']-=100
    elif tamper=='duration':schedule[0]['selected_duration_min']-=10
    elif tamper=='inventory':inv[1]['inventory_t']=-1
    elif tamper=='demand':rows[0]['kVA_bound']=0
    elif tamper=='pump':
        i=next(i for i,r in enumerate(rows) if r['furnace_on']);rows[i]['pump_on']=False;rows[i]['asset_run']['PMP_01']=False
    elif tamper=='stock_borrow':rows[0]['rolling_billet_t']=inp.initial_inventory_t+1
    elif tamper=='rolling_capacity':rows[0]['rolling_billet_t']=3
    elif tamper=='state':rows[0]['asset_run']['CMP_01']=False
    elif tamper=='cost':rows[0]['tariff_cost_Rs']=0
    elif tamper=='NaN':rows[0]['rolling_billet_t']=float('nan')
    elif tamper=='RHF':rows[0]['rhf_temperature_C']=1100
    elif tamper=='production':metrics['bars_t']=100
    elif tamper=='availability':
        availability=dict(inp.equipment_availability);availability['IF_01']=(False,)*96;inp=replace(inp,equipment_availability=availability)
    bad=replace(result,load_trajectory=rows,schedule=schedule,inventory_trajectory=inv,predicted_metrics=metrics)
    if tamper=='binding_slack':bad=replace(bad,active_constraints=dict(result.active_constraints,min_demand_slack_kVA=7000))
    elif tamper=='solver_objective':bad=replace(bad,solver_status=dict(result.solver_status,best_feasible_objective=0))
    elif tamper=='extra_hidden_field':rows[0]['latent_health']=1
    assert not check_schedule(inp,bad)['feasible']


def test_health_is_informational(inp,result):
    stressed=replace(inp,health_predictions=tuple(replace(p,failure_probability=.999,calibrated_probability=.999) for p in inp.health_predictions))
    r=optimize(stressed)
    assert r.releasable and r.schedule==result.schedule and r.load_trajectory==result.load_trajectory
    assert all(p['calibrated_probability']==.999 for p in r.health_context)


def test_explicit_SEC_cap(inp):
    constrained=replace(inp,constraints=replace(inp.constraints,sec_target_kWh_per_t=635))
    r=optimize(constrained);assert r.releasable
    assert r.predicted_metrics['predicted_IF_SEC_kWh_per_t']<=635
    assert optimize(constrained,practices=('normal',)).status=='infeasible'
