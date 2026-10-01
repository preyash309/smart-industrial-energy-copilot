"""Adversarial replay gates use physical outputs, not optimization expressions."""
from dataclasses import replace
from pathlib import Path
from copy import deepcopy
import json
import numpy as np
import pandas as pd
import pytest
from energy_copilot.common import load_config,values,sha256
from energy_copilot.sim import simulate as frozen
from energy_copilot.replay.compatible_v111 import simulate,InvariantError
from energy_copilot.replay.adapter import adapt_plan,ReplayControls
from energy_copilot.replay.runner import replay_case
from energy_copilot.replay.checker import verify_physics
from energy_copilot.replay.scenarios import scenario_proof
from energy_copilot.replay.origin_state import before_origin,frame_hash,TABLES
from energy_copilot.replay.history import posted_history
from energy_copilot.replay.compare import realized_metrics,paired_change
from energy_copilot.replay.attribution import robustness,attribution
from energy_copilot.replay.forecast_error import errors
from energy_copilot.optimization.contracts import input_from_dict,OptimizerResult
from scripts.phase2d import protected


@pytest.fixture(scope='module')
def context():
    cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    inp=replace(input_from_dict(json.loads(Path('plans/optimizer_v1/optimizer_input.json').read_text())),objective_mode='cost')
    plans={n:OptimizerResult(**json.loads((Path('plans/optimizer_v1')/n/'result.json').read_text())) for n in ('c3_tariff_normal','c4_tariff_synthetic','conservative_tariff_synthetic')}
    base=frozen(cfg,seed=42,days=30);proof=scenario_proof(cfg,42,30)
    control=adapt_plan(inp,plans['c3_tariff_normal'],cfg)
    good=simulate(cfg,schedule=control.schedule,seed=42,days=30,rolling_dispatch=control.rolling_dispatch)
    return cfg,inp,plans,base,proof,control,good


def test_upstream_protection():assert protected()['protected_files']>=936


def test_layer_explicit_diff():
    m=json.loads(Path('configs/replay_compatibility_manifest.json').read_text())
    assert sha256('src/energy_copilot/sim/engine.py')==m['frozen_source_sha256']
    assert sha256('src/energy_copilot/replay/compatible_v111.py')==m['layer_sha256']
    assert sha256('docs/phase2d_compatibility_diff.patch')==m['diff_sha256']
    assert not m['physical_equations_changed']


@pytest.mark.parametrize('seed',[42,201,210])
def test_default_regression(seed):
    cfg=load_config('data/processed/sim_v1.1/config_snapshot.yaml')
    a=frozen(cfg,seed=seed,days=2);b=simulate(cfg,seed=seed,days=2)
    assert a.summary==b.summary and a.scenario_manifest==b.scenario_manifest
    for n in TABLES:assert frame_hash(getattr(a,n))==frame_hash(getattr(b,n))


def test_adapter_exact_and_mode(context):
    cfg,inp,plans,base,proof,control,good=context
    assert control.schedule=={r['heat_id']:r['start'] for r in plans['c3_tariff_normal'].schedule}
    assert list(control.rolling_dispatch.values())==[r['rolling_billet_t'] for r in plans['c3_tariff_normal'].load_trajectory]
    synthetic=adapt_plan(inp,plans['c4_tariff_synthetic'],cfg)
    assert synthetic.practice_by_day=={7:40.0} and control.practice_by_day=={}


def test_partial_rolling_is_explicit(context):
    cfg,inp,plans,*_=context
    partial=adapt_plan(inp,plans['c3_tariff_normal'],cfg,rolling_policy='reference_partial')
    assert not partial.rolling_dispatch and partial.scope.startswith('heat-schedule replay only')
    with pytest.raises(ValueError):adapt_plan(inp,plans['c3_tariff_normal'],cfg,rolling_policy='silent')


def test_mixed_practice_fail_closed(context,monkeypatch):
    cfg,inp,plans,*_=context
    r=plans['c3_tariff_normal'];rows=[dict(x) for x in r.schedule];rows[-1]['selected_practice']='practice_loss_40'
    # Reach the mapping check independently of the unchanged upstream checker.
    import energy_copilot.replay.adapter as module
    monkeypatch.setattr(module,'check_schedule',lambda *_:dict(feasible=True))
    with pytest.raises(ValueError,match='Mixed'):adapt_plan(inp,replace(r,schedule=tuple(rows)),cfg)


def test_matched_origin_and_exogenous(context):
    cfg,inp,plans,base,proof,control,good=context
    assert before_origin(base,inp.forecast_origin)==before_origin(good,inp.forecast_origin)
    assert base.scenario_manifest['scenario_sha256']==good.scenario_manifest['scenario_sha256']==proof['scenario_sha256']
    assert proof['generated_before_decisions'] and set(proof['component_hashes'])>={'noise','rhf_zone_noise','rhf_flue_noise','wear','charge_loss'}
    assert before_origin(base,inp.forecast_origin)['inventory_t']==50


def test_same_seed_plan_byte_identical(context):
    cfg,inp,plans,base,proof,control,good=context
    b=simulate(cfg,schedule=control.schedule,seed=42,days=30,rolling_dispatch=control.rolling_dispatch)
    for n in TABLES:assert frame_hash(getattr(b,n))==frame_hash(getattr(good,n))
    assert b.scenario_manifest==good.scenario_manifest


def test_different_seeds_and_horizon_tapes(context):
    cfg,_,_,_,proof,*_=context
    assert proof['scenario_sha256']!=scenario_proof(cfg,201,30)['scenario_sha256']
    assert proof['component_hashes']['half']!=scenario_proof(cfg,42,8)['component_hashes']['half']


def test_actual_physical_constraints(context):
    cfg,inp,plans,base,proof,control,good=context
    v=verify_physics(good,inp,control)
    assert v['feasible'] and v['violations']==0
    for k in ('electricity_branch_to_main','whole_plant_mass','coal_NCV_energy','exact_piecewise_contract_demand','exact_piecewise_pump_interlock','replay_exact_starts','replay_exact_rolling','replay_bar_order'):
        assert v['checks'][k]==0
    assert 0<v['actual_day_peak_kVA']<=7000


@pytest.mark.parametrize('attack',['electricity','stock','demand','production','cooling'])
def test_independent_actual_checker_rejects_tampering(context,attack):
    cfg,inp,plans,base,proof,control,good=context
    x=deepcopy(good);i=inp
    mask=x.latent_truth.asset_id.eq('MAIN')&x.latent_truth.timestamp.eq(pd.Timestamp(inp.forecast_origin)+pd.Timedelta(hours=1))
    if attack=='electricity':x.latent_truth.loc[mask,'kWh']+=10
    elif attack=='stock':x.latent_truth.loc[mask,'yard_stock_t']=-1
    elif attack=='demand':i=replace(inp,constraints=replace(inp.constraints,demand_limit_kVA=3000))
    elif attack=='production':i=replace(inp,production_order=replace(inp.production_order,bars_t=120))
    else:
        x.latent_truth.loc[(x.latent_truth.asset_id=='PMP_01')&(x.latent_truth.timestamp==pd.Timestamp(inp.forecast_origin)+pd.Timedelta(hours=1)),'flow_m3_h']=0
    assert not verify_physics(x,i,control)['feasible']


def test_synthetic_only_after_origin_physics_coupled(context):
    cfg,inp,plans,base,proof,control,good=context
    s=simulate(cfg,seed=42,days=30,practice_by_day={7:40.0})
    assert before_origin(s,inp.forecast_origin)==before_origin(base,inp.forecast_origin)
    a=base.latent_heats[base.latent_heats.day.eq(7)];b=s.latent_heats[s.latent_heats.day.eq(7)]
    assert np.allclose(a.kWh.to_numpy()-b.kWh.to_numpy(),200,atol=1e-8,rtol=0)
    assert np.allclose(a.powered_min.to_numpy()-b.powered_min.to_numpy(),2.4,atol=1e-8,rtol=0)
    assert a.fault_label.tolist()==b.fault_label.tolist()


def test_failed_original_plan_retained(context):
    cfg,inp,plans,base,proof,*_=context
    control=adapt_plan(inp,plans['c4_tariff_synthetic'],cfg)
    entry,sim=replay_case('S3',base,inp,control,42,30,proof,result=plans['c4_tariff_synthetic'])
    assert sim is None and entry['status']=='replay_infeasible' and entry['retained']
    assert entry['realized_metrics'] is None and '1440.47' in entry['violation']
    assert entry['matched_conditions']['prefix_heat_state_identical'] and not entry['decision_mutation']


def test_invalid_rolling_feed_not_clipped(context):
    cfg,*_=context
    with pytest.raises(InvariantError,match='Requested rolling exceeds'):
        simulate(cfg,seed=42,days=30,rolling_dispatch={7*96:3.0})


def test_controls_cannot_modify_shared_history(context):
    cfg,inp,plans,base,proof,control,good=context
    with pytest.raises(ValueError,match='common history'):
        replay_case('bad',base,inp,replace(control,practice_by_day={0:40}),42,30,proof)
    with pytest.raises(ValueError,match='all slots'):
        replay_case('bad',base,inp,replace(control,rolling_dispatch={7*96:2}),42,30,proof)


def test_past_only_public_history(context):
    cfg,inp,plans,base,*_=context
    a=posted_history(base.readings,base.heats,base.production,values(cfg),inp.forecast_origin)
    readings=base.readings.copy();heats=base.heats.copy();production=base.production.copy()
    readings.loc[readings.timestamp>=pd.Timestamp(inp.forecast_origin),'kW']=1e10
    heats.loc[heats.end>pd.Timestamp(inp.forecast_origin),'kWh']=1e10
    production.loc[pd.to_datetime(production.date)>=pd.Timestamp(inp.forecast_origin),'yard_stock_t']=1e10
    b=posted_history(readings,heats,production,values(cfg),inp.forecast_origin)
    assert a==b
    source=Path('src/energy_copilot/replay/history.py').read_text()
    assert 'latent_truth' not in source and 'events.parquet' not in source


def test_meter_tariff_from_realized_only(context):
    cfg,inp,plans,base,proof,control,good=context
    m,ledger=realized_metrics(good,inp,verify_physics(good,inp,control))
    assert m['QC_meter_coverage']<1 and ledger.realized_QC_meter_kWh.isna().any()
    expected=(ledger.realized_QC_meter_kWh*ledger.tariff_Rs_per_kWh).sum()
    assert abs(expected-m['QC_known_meter_tariff_cost_Rs'])<1e-8
    assert abs(m['physical_evaluation_tariff_cost_Rs']-plans['c3_tariff_normal'].predicted_metrics['predicted_tariff_cost_Rs'])>1
    assert m['label']=='DIGITAL-TWIN-REALIZED' and m['physical_evaluation_only']


def test_tariff_cost_never_changes_energy(context):
    cfg,inp,plans,base,proof,control,good=context
    m,_=realized_metrics(good,inp,verify_physics(good,inp,control))
    p=dict(m,physical_evaluation_tariff_cost_Rs=m['physical_evaluation_tariff_cost_Rs']*.9,QC_known_meter_tariff_cost_Rs=m['QC_known_meter_tariff_cost_Rs']*.9)
    result=paired_change(m,p)
    assert result['kWh_reduction']==0 and result['physical_evaluation_cost_reduction_pct']==pytest.approx(10)


def test_error_arithmetic_and_failure_denominators():
    x=errors([10,20],[8,23],[11,19]);assert x['MAE']==2.5 and x['bias_actual_minus_p50']==-.5 and x['p90_exceedance']==.5
    m=dict(total_kWh=100,physical_evaluation_tariff_cost_Rs=100,QC_known_meter_tariff_cost_Rs=100,QC_meter_coverage=1,bar_t=1,plant_kWh_per_t_bars=100)
    ok=dict(status='physically_valid',realized_metrics=m);bad=dict(status='replay_infeasible',realized_metrics=None)
    run1={n:ok for n in ('S0','S1','S2','S3','conservative_normal','conservative_synthetic')};run2=dict(run1,S1=bad)
    result=robustness({'1':run1,'2':run2})
    assert result['S1']['total_scenarios']==2 and result['S1']['feasible_pct']==50
    assert attribution(run2)['bridge']['status'].startswith('incomplete')


@pytest.mark.parametrize('attack',['seed','horizon','practice','identity'])
def test_replay_input_identity_fail_closed(context,attack):
    cfg,inp,plans,base,proof,control,good=context
    if attack=='seed':
        with pytest.raises(ValueError,match='seed/horizon'):replay_case('bad',base,inp,control,201,30,proof)
    elif attack=='horizon':
        with pytest.raises(ValueError,match='seed/horizon'):replay_case('bad',base,inp,control,42,8,proof)
    elif attack=='practice':
        with pytest.raises(ValueError,match='Unsupported practice'):replay_case('bad',base,inp,replace(control,practice_by_day={7:41}),42,30,proof)
    else:
        with pytest.raises(ValueError,match='identities'):replay_case('bad',base,inp,replace(control,schedule={'D000_H00':inp.forecast_origin}),42,30,proof)


def test_retained_evaluation_artifact_gate():
    out=Path('replay/optimizer_v1');ex=json.loads((out/'experiment.json').read_text())
    assert ex['evaluation_seeds']==list(range(201,211)) and ex['complete_decision_loop']
    assert ex['primary']['S3']['status']=='replay_infeasible'
    failures=pd.read_parquet(out/'failure_analysis.parquet')
    assert len(failures[failures.status.ne('diagnostic')])==25
    assert failures.retained.all()
    for s in range(201,211):
        cases=json.loads((out/'evaluation'/f'seed_{s}'/'case_results.json').read_text())
        assert set(cases)=={'S0','S1','S2','S3','conservative_normal','conservative_synthetic'}
        for e in cases.values():
            if e['status']=='physically_valid':assert e['verification']['feasible'] and e['matched_conditions']['status']=='PASS'


def test_prediction_realization_schema_separation():
    p=Path('replay/optimizer_v1/primary/optimized/c3_tariff_normal')
    h=pd.read_parquet(p/'heat_forecast_comparison.parquet');load=pd.read_parquet(p/'load_forecast_comparison.parquet')
    assert {'actual_energy_kWh','energy_p50_kWh','energy_p90_kWh','actual_duration_min'}<=set(h)
    assert {'actual_MAIN_kW','predicted_selected_MAIN_kW','actual_piecewise_kVA','predicted_kVA_bound'}<=set(load)
    result=json.loads((p/'optimizer_result.json').read_text())
    assert 'actual_energy_kWh' not in result['schedule'][0]
    assert 'realized_metrics' not in result
