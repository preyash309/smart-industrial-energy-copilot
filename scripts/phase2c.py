"""Planning demo. Historical public observations are predicate-filtered BEFORE loading.

No simulator replay, evaluation prediction Parquets or hidden/event tables are read.
"""
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from energy_copilot.common import sha256,write_json
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization import ProductionOrder,HeatOrder,TariffSlot,build_optimizer_input,load_settings,optimize
from energy_copilot.optimization.contracts import ASSETS,timestamp


def verify_frozen():
    hashes=json.loads(Path('configs/phase2c_readonly_manifest.json').read_text())
    changed=[p for p,digest in hashes.items() if sha256(p)!=digest]
    if changed:raise RuntimeError('Frozen inputs changed: '+str(changed))
    return dict(status='PASS',protected_files=len(hashes))


def contexts_from_history(slots,heats,register,origin):
    origin=pd.Timestamp(origin)
    for table in (slots,heats,register):
        if table.empty or table.available_at.isna().any() or table.available_at.gt(origin).any():raise ValueError('Empty/late public history')
    slots=slots.sort_values('interval_start').reset_index(drop=True);heats=heats.sort_values('end_time')
    if slots.iloc[-1].interval_end!=origin or len(slots)<97 or not slots.interval_start.diff().dropna().eq(pd.Timedelta(minutes=15)).all():raise ValueError('Incomplete posted history')
    if not slots.available_at.ge(slots.interval_end).all() or not heats.available_at.ge(heats.end_time).all() or not register.available_at.ge(register.interval_end).all():raise ValueError('Impossible public posting timestamp')
    latest=slots.iloc[-1]; at=origin.isoformat()
    def clean(x):return None if pd.isna(x) else float(x)
    def mean(x):return clean(x.mean())
    f=dict(previous_heat_SEC=clean(heats.iloc[-1].SEC_kWh_per_t),previous_heat_duration=clean(heats.iloc[-1].duration_min),
           rolling_mean_SEC=mean(heats.SEC_kWh_per_t.tail(20)),global_mean_SEC=mean(heats.SEC_kWh_per_t),
           historical_duration_mean=mean(heats.duration_min),context_PMP_01_flow_m3_h=clean(latest.PMP_01_flow_m3_h),
           context_MILL_01_vibration_mm_s=clean(latest.MILL_01_vibration_mm_s))
    heat=dict(features=f,available_at={k:at for k in f})
    x=slots.AUX_kW;lf={f'load_lag_{k}':clean(x.iloc[-k]) for k in (1,2,4,96)}
    for w in (4,96):
        lf[f'load_past_{w}_mean']=mean(x.tail(w));lf[f'load_past_{w}_std']=clean(x.tail(w).std(ddof=0))
    seasonal=[dict(value=clean(v),available_at=pd.Timestamp(post).isoformat()) for v,post in zip(x.tail(96),slots.available_at.tail(96))]
    load=dict(features=lf,available_at={k:at for k in lf},seasonal_profile=seasonal)
    health=[]
    for asset,channels in [('MILL_01',('vibration_mm_s','temp_C','kW','rpm')),('PMP_01',('vibration_mm_s','temp_C','kW','flow_m3_h'))]:
        hf={}
        for channel in channels:
            series=slots[f'{asset}_{channel}'];hf[channel]=clean(series.iloc[-1])
            for w in (4,96):
                past=series.iloc[:-1].tail(w);hf[f'{channel}_past_{w}_mean']=mean(past);hf[f'{channel}_past_{w}_std']=clean(past.std(ddof=0))
            hf[f'{channel}_change_24h']=clean(series.iloc[-1]-series.iloc[-97])
        hf['runtime_past_24h']=float(slots[f'{asset}_state'].iloc[:-1].tail(96).eq('running').sum()*.25)
        health.append(dict(asset_id=asset,forecast_origin=at,features=hf,available_at={k:at for k in hf}))
    stock=register.sort_values('available_at').iloc[-1]
    return heat,load,tuple(health),float(stock.yard_stock_t),dict(source='analytics_v1',forecast_origin=at,
        slot_history_rows=len(slots),completed_heat_rows=len(heats),inventory_available_at=pd.Timestamp(stock.available_at).isoformat(),
        inventory_source='last published shift-close register',no_future_rows_loaded=True)


def read_history(origin):
    origin=timestamp(origin); directory=Path('data/processed/analytics_v1')
    columns=['interval_start','interval_end','available_at','AUX_kW']
    for asset,channels in [('MILL_01',('vibration_mm_s','temp_C','kW','rpm','state')),('PMP_01',('vibration_mm_s','temp_C','kW','flow_m3_h','state'))]:
        columns.extend(f'{asset}_{ch}' for ch in channels)
    slots=pq.read_table(directory/'slot_features.parquet',columns=columns,filters=[('available_at','<=',origin)]).to_pandas()
    heats=pq.read_table(directory/'heat_features.parquet',columns=['end_time','available_at','SEC_kWh_per_t','duration_min'],filters=[('available_at','<=',origin)]).to_pandas()
    reg=pq.read_table(directory/'production_register.parquet',columns=['interval_end','available_at','yard_stock_t'],filters=[('available_at','<=',origin)]).to_pandas()
    return contexts_from_history(slots,heats,reg,origin)


def reference_input(origin='2026-01-12T00:00:00'):
    cfg,p,c=load_settings();heat,load,health,inventory,provenance=read_history(origin)
    start=timestamp(origin);n=c.horizon_slots
    availability={a:tuple(True for _ in range(n)) for a in ASSETS}
    working=start.weekday() not in p['calendar']['off_weekdays']
    windows={a:tuple(working if a=='IF_01' else True for _ in range(n)) for a in ASSETS}
    millmask=tuple(working and p['calendar']['mill_start_hour']<=t*c.slot_minutes/60<p['calendar']['mill_start_hour']+p['calendar']['mill_hours'] for t in range(n))
    windows['MILL_01']=millmask; windows['RHF_01']=millmask
    rates=cfg['tariff']['period_rates']; tariffs=[]
    for t in range(n):
        lo=start+timedelta(minutes=t*c.slot_minutes);hi=lo+timedelta(minutes=c.slot_minutes);hour=t*c.slot_minutes/60
        peak=cfg['tariff']['peak_hours'];off=cfg['tariff']['offpeak_hours']
        period='peak' if peak[0]<=hour<peak[1] else 'offpeak' if off[0]<=hour<off[1] or off[2]<=hour<off[3] else 'normal'
        tariffs.append(TariffSlot(lo.isoformat(),hi.isoformat(),period,rates[period]))
    order=ProductionOrder(p['material']['bar_target'],p['material']['billet_target'],inventory)
    # Identity uses known configured calendar, never future event/heat tables.
    day=(start-timestamp(p['start'])).days
    heats=tuple(HeatOrder(f'D{day:03d}_H{i:02d}',p['if']['liquid_per_heat']) for i in range(p['calendar']['heats_per_day']))
    inp=build_optimizer_input(PredictionService(cfg['prediction_directory']),origin,order,inventory,heats,heat,load,tariffs,rates,
        cfg['tariff']['version'],cfg['tariff']['source'],availability,windows,health)
    return inp,provenance


def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['C1','all'],default='C1');args=ap.parse_args()
    protected=verify_frozen();inp,provenance=reference_input()
    r=optimize(inp,practices=('normal',))
    Path('plans/optimizer_v1').mkdir(parents=True,exist_ok=True)
    write_json('plans/optimizer_v1/c1_feasibility.json',r.to_dict())
    write_json('plans/optimizer_v1/origin_provenance.json',provenance)
    print('C1',r.status,'independent checker',r.checker.get('feasible'),r.reason)
    if not r.releasable:raise RuntimeError('C1 gate failed; do not proceed')
    if args.stage=='all':
        from scripts.phase2c_release import release
        release(inp,provenance,protected,r)
    verify_frozen()


if __name__=='__main__': main()
