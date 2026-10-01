"""Fail-closed boundaries and public PredictionService integration."""
from dataclasses import replace
from pathlib import Path
from dataclasses import asdict
import json
import ast
import pytest
from scripts.phase2c import reference_input,verify_frozen
from energy_copilot.optimization import optimize
from energy_copilot.optimization.candidates import build_optimizer_input


@pytest.fixture(scope='module')
def inp():return reference_input()[0]


@pytest.mark.parametrize('kind',['late_heat','late_load','fallback_heat','fallback_flag_type','fallback_load','wrong_version','schema','bad_inventory','bad_order','unknown_practice','unknown_tariff','main_forecast','nan_energy','crossed_quantiles','wrong_SEC','timezone','load_gap','unknown_asset'])
def test_contract_rejects(inp,kind):
    altered=inp
    if kind in ('late_heat','fallback_heat','fallback_flag_type','wrong_version','unknown_practice','nan_energy','crossed_quantiles','wrong_SEC'):
        k=inp.heat_candidates[0];p=k.prediction
        change={'late_heat':dict(available_at='2026-01-12T00:01:00'),'fallback_heat':dict(status='fallback',usable_for_constraints=False),'fallback_flag_type':dict(usable_for_constraints='True'),
                'wrong_version':dict(model_version='unqualified_v2'),'unknown_practice':dict(practice_mode='best_safe'),
                'nan_energy':dict(energy_p50_kWh=float('nan')),'crossed_quantiles':dict(energy_p10_kWh=p.energy_p90_kWh+1),
                'wrong_SEC':dict(SEC_p50=1)}[kind]
        altered=replace(inp,heat_candidates=(replace(k,prediction=replace(p,**change)),)+inp.heat_candidates[1:])
    elif kind in ('late_load','fallback_load','main_forecast'):
        p=inp.background_load_forecast[0]
        change={'late_load':dict(available_at='2026-01-12T00:01:00'),'fallback_load':dict(usable_for_constraints=False,status='fallback'),'main_forecast':dict(components=('MAIN',))}[kind]
        altered=replace(inp,background_load_forecast=(replace(p,**change),)+inp.background_load_forecast[1:])
    elif kind=='schema':altered=replace(inp,prediction_schema_sha256='0'*64)
    elif kind=='bad_inventory':altered=replace(inp,initial_inventory_t=201)
    elif kind=='bad_order':altered=replace(inp,production_order=replace(inp.production_order,bars_t=-1))
    elif kind=='unknown_tariff':altered=replace(inp,tariff_calendar=(replace(inp.tariff_calendar[0],period='undeclared'),)+inp.tariff_calendar[1:])
    elif kind=='timezone':altered=replace(inp,forecast_origin='2026-01-12T00:00:00+05:30')
    elif kind=='load_gap':altered=replace(inp,background_load_forecast=inp.background_load_forecast[:-1])
    elif kind=='unknown_asset':altered=replace(inp,equipment_availability={**inp.equipment_availability,'UNKNOWN':(True,)*96})
    with pytest.raises(ValueError):optimize(altered)


def test_prediction_service_is_required():
    with pytest.raises(TypeError,match='PredictionService'):
        build_optimizer_input(None,None,None,None,None,None,None,None,None,None,None,None,None)


def test_optimization_source_has_no_training_or_table_readers():
    for path in Path('src/energy_copilot/optimization').glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else ''
                assert name not in ('fit','train','read_parquet','read_table','simulate','joblib.load')
        text=path.read_text()
        assert 'predictions/test_' not in text and 'latent_truth.parquet' not in text and 'events.parquet' not in text


def test_frozen_protection():assert verify_frozen()['status']=='PASS'


def test_input_serialization_roundtrip(inp):
    from energy_copilot.optimization import input_from_dict
    loaded=input_from_dict(json.loads(json.dumps(asdict(inp))))
    assert asdict(loaded)==asdict(inp)
    assert optimize(loaded).releasable
