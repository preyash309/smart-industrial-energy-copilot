from dataclasses import replace
from datetime import timedelta
import math
import pytest
from scripts.phase2c import reference_input
from energy_copilot.optimization import optimize,HeatCandidate,TariffSlot,ProductionOrder
from energy_copilot.optimization.contracts import timestamp
from energy_copilot.optimization.baseline import baseline_schedule


@pytest.fixture(scope='module')
def inp():return reference_input()[0]


def test_known_analytical_toy(inp):
    # One 10-t heat, exactly coupled synthetic intervention, two start choices.
    # Public typed predictions here are hand-authored toy coefficients, never a
    # production alternative to PredictionService or evaluation-file inputs.
    origin=timestamp(inp.forecast_origin);heat=inp.heats[:1];p=inp.heat_candidates[0].prediction;ks=[]
    for minute in (0,720):
        for mode,e,d in [('normal',6500.,105.),('practice_loss_40',6300.,102.6)]:
            pred=replace(p,practice_mode=mode,energy_p10_kWh=e,energy_p50_kWh=e,energy_p90_kWh=e,SEC_p50=e/10,
                         duration_p10_min=d,duration_p50_min=d,duration_p90_min=d)
            ks.append(HeatCandidate(f'{mode}-{minute}',heat[0].heat_id,(origin+timedelta(minutes=minute)).isoformat(),pred))
    tariffs=tuple(TariffSlot(t.interval_start,t.interval_end,'high' if i<48 else 'low',10 if i<48 else 1) for i,t in enumerate(inp.tariff_calendar))
    background=tuple(replace(p,load_p10_kW=250.,load_p50_kW=250.,load_p90_kW=250.) for p in inp.background_load_forecast)
    toy=replace(inp,heats=heat,heat_candidates=tuple(ks),production_order=ProductionOrder(9.12,9.5,50),
                background_load_forecast=background,tariff_calendar=tariffs,tariff_period_rates={'high':10,'low':1},tariff_version='analytical_toy',objective_mode='cost')
    result=optimize(toy)
    assert result.releasable and result.status=='optimal'
    assert result.schedule[0]['start']=='2026-01-12T12:00:00'
    assert result.schedule[0]['selected_practice']=='practice_loss_40'
    # AUX 33000, pump 9900, RHF 4960, compressor 10880, IF 6300,
    # mill 912. Entire bar production can run in low-tariff 12:00-16:00.
    assert result.predicted_metrics['predicted_tariff_cost_Rs']==pytest.approx(65952,abs=1e-6)


def test_accounting_and_no_double_counting(inp):
    result=optimize(replace(inp,objective_mode='cost'))
    assert result.releasable
    furnace=sum(r['selected_energy_kWh'] for r in result.schedule)
    assert sum(r['asset_kWh']['IF_01'] for r in result.load_trajectory)==pytest.approx(furnace,abs=1e-6)
    for r,p in zip(result.load_trajectory,inp.background_load_forecast):
        assert sum(r['asset_kWh'].values())==pytest.approx(r['total_kWh'])
        assert r['asset_kWh']['AUX']==pytest.approx(p.load_p50_kW*.25)
        assert r['average_kVA']<=r['kVA_bound']+1e-6
    independent_cost=sum(r['total_kWh']*t.Rs_per_kWh for r,t in zip(result.load_trajectory,inp.tariff_calendar))
    assert independent_cost==pytest.approx(result.predicted_metrics['predicted_tariff_cost_Rs'])
    assert result.checker['mass_residual_t']==pytest.approx(0,abs=1e-6)
    assert result.checker['energy_residual_kWh']==pytest.approx(0,abs=1e-6)


def test_flat_tariff_equals_energy_objective(inp):
    rates={'flat':3.0};tariffs=tuple(replace(t,period='flat',Rs_per_kWh=3.) for t in inp.tariff_calendar)
    flat=replace(inp,tariff_period_rates=rates,tariff_calendar=tariffs,tariff_version='flat_v1',objective_mode='cost')
    cost=optimize(flat);energy=optimize(replace(flat,objective_mode='energy'))
    assert cost.releasable and energy.releasable
    assert cost.predicted_metrics['predicted_tariff_cost_Rs']==pytest.approx(3*energy.predicted_metrics['predicted_total_kWh'],abs=1e-6)


def test_explanations_reconcile_to_objective_evidence(inp):
    from energy_copilot.optimization.explain import explanation_data
    x=replace(inp,objective_mode='cost');r=optimize(x);b=baseline_schedule(x)
    assert len(r.explanation_data)==len(inp.heats)
    rows=explanation_data(x,r,b)
    delta=sum(v['predicted_IF_cost_delta_Rs'] for v in rows)
    actual=sum((a['asset_kWh']['IF_01']-old['asset_kWh']['IF_01'])*t.Rs_per_kWh for a,old,t in zip(r.load_trajectory,b.load_trajectory,inp.tariff_calendar))
    assert delta==pytest.approx(actual,abs=1e-6)
