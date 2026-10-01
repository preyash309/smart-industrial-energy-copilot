from dataclasses import replace
import pytest
from scripts.phase2c import reference_input
from energy_copilot.optimization import optimize


@pytest.fixture(scope='module')
def inp():return reference_input()[0]


@pytest.mark.parametrize('case',['IF_unavailable','pump_unavailable','mill_unavailable','RHF_unavailable','excess_production','insufficient_billets','demand','SEC','closing_stock'])
def test_explicit_infeasibility(inp,case):
    if case.endswith('_unavailable'):
        a={'IF_unavailable':'IF_01','pump_unavailable':'PMP_01','mill_unavailable':'MILL_01','RHF_unavailable':'RHF_01'}[case]
        avail=dict(inp.equipment_availability);avail[a]=(False,)*96;inp=replace(inp,equipment_availability=avail)
    elif case=='excess_production':inp=replace(inp,production_order=replace(inp.production_order,bars_t=200))
    elif case=='insufficient_billets':inp=replace(inp,production_order=replace(inp.production_order,billets_t=130))
    elif case=='demand':inp=replace(inp,constraints=replace(inp.constraints,demand_limit_kVA=500))
    elif case=='SEC':inp=replace(inp,constraints=replace(inp.constraints,sec_target_kWh_per_t=500))
    elif case=='closing_stock':inp=replace(inp,production_order=replace(inp.production_order,final_inventory_min_t=100))
    r=optimize(inp)
    assert r.status=='infeasible' and not r.releasable and r.reason
    assert not r.schedule and not r.predicted_metrics
