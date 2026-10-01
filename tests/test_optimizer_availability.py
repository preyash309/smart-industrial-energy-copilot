from dataclasses import replace
from pathlib import Path
import copy
import pandas as pd
import pyarrow.parquet as pq
import pytest
from scripts.phase2c import reference_input,contexts_from_history
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization import optimize


def public_prefix():
    origin=pd.Timestamp('2026-01-12');d=Path('data/processed/analytics_v1')
    cols=['interval_start','interval_end','available_at','AUX_kW']
    for a,chs in [('MILL_01',('vibration_mm_s','temp_C','kW','rpm','state')),('PMP_01',('vibration_mm_s','temp_C','kW','flow_m3_h','state'))]:cols.extend(f'{a}_{ch}' for ch in chs)
    s=pq.read_table(d/'slot_features.parquet',columns=cols,filters=[('available_at','<=',origin.to_pydatetime())]).to_pandas()
    h=pq.read_table(d/'heat_features.parquet',columns=['end_time','available_at','SEC_kWh_per_t','duration_min'],filters=[('available_at','<=',origin.to_pydatetime())]).to_pandas()
    r=pq.read_table(d/'production_register.parquet',columns=['interval_end','available_at','yard_stock_t'],filters=[('available_at','<=',origin.to_pydatetime())]).to_pandas()
    return s,h,r,origin


def test_no_end_measurement_available_at_start():
    s,h,r,origin=public_prefix();s.loc[s.index[-1],'available_at']+=pd.Timedelta(minutes=5)
    with pytest.raises(ValueError,match='late'):contexts_from_history(s,h,r,origin)


def test_null_history_is_not_filled_from_hidden_truth():
    s,h,r,origin=public_prefix();s.loc[s.index[-1],'PMP_01_flow_m3_h']=float('nan')
    heat,_,health,_,_=contexts_from_history(s,h,r,origin)
    assert heat['features']['context_PMP_01_flow_m3_h'] is None and health[1]['features']['flow_m3_h'] is None
    service=PredictionService('models/phase2b_v1')
    risk=service.predict_health(health[1],24)
    assert 0<=risk.calibrated_probability<=1


def test_service_rejects_future_and_hidden_context():
    s,h,r,origin=public_prefix();_,load,_,_,_=contexts_from_history(s,h,r,origin)
    service=PredictionService('models/phase2b_v1')
    late=copy.deepcopy(load);late['available_at']['load_lag_1']='2026-01-12T00:15:00'
    with pytest.raises(ValueError,match='Late'):service.predict_background_load(origin.isoformat(),96,late)
    hidden=copy.deepcopy(load);hidden['features']['latent_fouling']=0;hidden['available_at']['latent_fouling']=origin.isoformat()
    with pytest.raises(ValueError,match='schema'):service.predict_background_load(origin.isoformat(),96,hidden)


def test_future_rows_are_rejected_before_features():
    s,h,r,origin=public_prefix();future=s.iloc[-1:].copy();future['interval_start']+=pd.Timedelta(days=1);future['interval_end']+=pd.Timedelta(days=1);future['available_at']+=pd.Timedelta(days=1)
    with pytest.raises(ValueError,match='late'):contexts_from_history(pd.concat([s,future]),h,r,origin)


def test_missing_artifact_fallback_cannot_reach_solver(monkeypatch):
    original=Path.exists
    def exists(path):
        return False if path.name=='production.joblib' and path.parent.name=='heat_energy' else original(path)
    monkeypatch.setattr(Path,'exists',exists)
    with pytest.raises(ValueError,match='fallback'):reference_input()


def test_repeated_cost_inputs_produce_identical_outputs():
    inp=replace(reference_input()[0],objective_mode='cost')
    a=optimize(inp);b=optimize(inp)
    assert a.releasable and a.to_dict()==b.to_dict()
