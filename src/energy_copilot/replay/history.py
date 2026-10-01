"""Prediction input builder receives ONLY filtered public past, never truth/events."""
from dataclasses import replace
from datetime import timedelta
import pandas as pd
import numpy as np
from energy_copilot.common import values
from energy_copilot.schema import ALLOWED_OBS_FEATURES
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization import build_optimizer_input
from scripts.phase2c import contexts_from_history


def posted_history(readings,heats,production,config,origin):
    # Project and filter before feature calculation; future frames discarded here.
    origin=pd.Timestamp(origin);step=config['clock_minutes']
    r=readings.loc[readings.timestamp+pd.Timedelta(minutes=step)<=origin,
                   ['timestamp','asset_id','sensor_glitch',*ALLOWED_OBS_FEATURES]].copy()
    r['interval_start']=r.timestamp;r['interval_end']=r.timestamp+pd.Timedelta(minutes=step);r['available_at']=r.interval_end
    selected=['interval_start','interval_end','available_at']
    slots=r[r.asset_id.eq('AUX')][selected].reset_index(drop=True)
    for asset,channels in [('AUX',('kW',)),('MILL_01',('vibration_mm_s','temp_C','kW','rpm','state')),('PMP_01',('vibration_mm_s','temp_C','kW','flow_m3_h','state'))]:
        x=r[r.asset_id.eq(asset)].sort_values('timestamp')
        for ch in channels:
            v=x[ch] if ch=='state' else x[ch].where(np.isfinite(x[ch])&~x.sensor_glitch)
            slots[f'{asset}_{ch}']=v.to_numpy()
    h=heats.loc[heats.end<=origin,['end','start','kWh','liquid_t']].copy()
    h['end_time']=h.end;h['available_at']=h.end;h['duration_min']=(h.end-h.start).dt.total_seconds()/60;h['SEC_kWh_per_t']=h.kWh/h.liquid_t
    p=production[['date','shift','yard_stock_t']].copy();p['interval_end']=pd.to_datetime(p.date)+pd.to_timedelta((p['shift'].astype(int)+1)*8,unit='h')
    p=p[p.interval_end<=origin].copy();p['available_at']=p.interval_end
    return contexts_from_history(slots,h[['end_time','available_at','duration_min','SEC_kWh_per_t']],p[['interval_end','available_at','yard_stock_t']],origin)


def seed_input(template, readings,heats,production,config,service):
    heat,load,health,inventory,provenance=posted_history(readings,heats,production,config,template.forecast_origin)
    inp=build_optimizer_input(service,template.forecast_origin,template.production_order,inventory,template.heats,
        heat,load,template.tariff_calendar,template.tariff_period_rates,template.tariff_version,template.tariff_source,
        template.equipment_availability,template.operating_windows,health,mode='central',objective='cost')
    return inp,provenance

