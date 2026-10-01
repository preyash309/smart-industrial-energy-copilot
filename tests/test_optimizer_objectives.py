from dataclasses import replace
import pytest
from scripts.phase2c import reference_input
from energy_copilot.optimization import optimize
from energy_copilot.optimization.baseline import baseline_schedule


@pytest.fixture(scope='module')
def inp():return reference_input()[0]


def test_c2_energy_gate(inp):
    plan=replace(inp,objective_mode='energy');base=baseline_schedule(plan);result=optimize(plan,practices=('normal',))
    assert base.releasable and result.releasable
    assert result.predicted_metrics['predicted_total_kWh']<=base.predicted_metrics['predicted_total_kWh']+1e-6


def test_c3_tariff_gate(inp):
    plan=replace(inp,objective_mode='cost');base=baseline_schedule(plan);result=optimize(plan,practices=('normal',))
    assert base.releasable and result.releasable
    assert result.predicted_metrics['predicted_tariff_cost_Rs']<=base.predicted_metrics['predicted_tariff_cost_Rs']+1e-6
