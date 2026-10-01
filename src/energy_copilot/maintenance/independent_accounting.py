"""Independent successor ledger arithmetic, including synthetic asset downtime.

No simulator calculations are imported. Config is passed explicitly so release
checks use the actual snapshot rather than live/default simulator parameters.
"""
import numpy as np
import pandas as pd

ASSETS = ["IF_01", "RHF_01", "MILL_01", "PMP_01", "CMP_01", "AUX"]
TOL = 1e-8


def unwrap(node):
    if isinstance(node, dict):
        return node["value"] if "value" in node else {k: unwrap(v) for k, v in node.items()}
    if isinstance(node, list):
        return [unwrap(v) for v in node]
    return node


def maxerr(a,b): return float(np.max(np.abs(np.asarray(a,dtype=float)-np.asarray(b,dtype=float)))) if len(a) else 0.


def reconstruct_segments(heats,events,config):
    """Independent piecewise integration from heat energy and documented fault duty."""
    C=unwrap(config); START=pd.Timestamp(C["start"])
    failures=events[(events.asset_id=='PMP_01')&events.type.isin(('failure','preventive_service','preventive_restart'))]
    repairs=[((r.start-START)/pd.Timedelta(minutes=1),(r.end-START)/pd.Timedelta(minutes=1)) for r in failures.itertuples()]
    segments=[]
    for h in heats.itertuples():
        cursor=(h.start-START)/pd.Timedelta(minutes=1)+h.nonpowered_min
        low_energy=C['if']['rated_kw']*C['faults']['half_fraction']*C['faults']['half_minutes']/60 if 'half' in h.fault_label.split('|') else 0.
        stages=[(low_energy,C['if']['rated_kw']*C['faults']['half_fraction']),(h.kWh-low_energy,C['if']['rated_kw'])]
        for energy,power in stages:
            remaining=energy
            while remaining>1e-9:
                active=next(((a,b) for a,b in repairs if a-1e-10<=cursor<b-1e-10),None)
                if active:
                    cursor=active[1];continue
                next_failure=min([a for a,b in repairs if a>cursor+1e-10]+[float('inf')])
                finish=cursor+remaining/power*60
                end=min(finish,next_failure)
                segments.append((cursor,end,power,h.heat_id))
                remaining-=power*(end-cursor)/60;cursor=end
        if abs(cursor-(h.end-START)/pd.Timedelta(minutes=1))>1e-7:
            raise RuntimeError(f'Independent heat end mismatch {h.heat_id}')
    return segments


def independent(tables,config,detail=False):
    C=unwrap(config); START=pd.Timestamp(C["start"]); STEP=C["clock_minutes"]; DT=STEP/60
    t=tables['latent_truth'];h=tables['latent_heats'];e=tables['events'];p=tables['production']
    site=t[t.asset_id=='MAIN'].sort_values('timestamp').set_index('timestamp')
    a=t[t.asset_id!='MAIN']; wide={x:t[t.asset_id==x].sort_values('timestamp').set_index('timestamp') for x in ASSETS}
    slots=site.index; day=slots.normalize()
    work=np.array([x.dayofweek not in C['calendar']['off_weekdays'] and x.strftime('%Y-%m-%d') not in C['calendar']['maintenance_dates'] for x in day])
    wd=sorted(set(day[work])); checks={};errors={}
    def residual(name,left,right):
        err=maxerr(left,right);errors[name]=err;checks[name]=int(np.count_nonzero(np.abs(np.asarray(left)-np.asarray(right))>TOL))
    def count(name,condition): checks[name]=int(np.count_nonzero(~np.asarray(condition,dtype=bool)))
    count('asset_slot_cardinality',t.groupby('timestamp').size().reindex(slots).eq(7))
    count('unique_asset_timestamp',~t.duplicated(['timestamp','asset_id']))
    count('15_minute_clock',site.index.to_series().diff().dropna().eq(pd.Timedelta(minutes=STEP)))
    residual('working_calendar',site.working_day.astype(int),work.astype(int))
    branch=a.groupby('timestamp').kWh.sum().reindex(slots)
    residual('electricity_branch_to_main',branch,site.kWh)
    residual('kWh_equals_kW_times_hours',t.kWh,t.kW*DT)
    residual('apparent_energy_units',t.kVAh,t.kVA*DT)
    residual('feeder_kVA_from_P_and_PF',a.kVA,a.kW/a.pf)
    q=sum(wide[x].kW*np.sqrt(1/wide[x].pf**2-1) for x in ASSETS)
    totalp=sum(wide[x].kW for x in ASSETS)
    residual('main_P_from_branches',site.kW,totalp)
    residual('main_kVA_vector_sum',site.kVA,np.sqrt(totalp**2+q**2))
    residual('main_PF',site.pf,totalp/np.sqrt(totalp**2+q**2))
    residual('IF_total_heat_energy',[wide['IF_01'].kWh.sum()],[h.kWh.sum()])
    residual('IF_component_energy',h.kWh,h.best_kWh+h.practice_kWh+h.fault_kWh)
    residual('heat_SEC',h.kWh_per_t,h.kWh/h.liquid_t)
    residual('melt_input_from_heat',h.charge_t,h.liquid_t/C['if']['melt_yield'])
    residual('caster_from_heat',h.billet_t,h.liquid_t*C['material']['cast_yield'])
    expected=np.zeros((len(site),3))
    for heat in h.itertuples():
        ix=int(np.ceil((heat.end-START)/pd.Timedelta(minutes=STEP))-1)
        expected[ix]+=[heat.charge_t,heat.liquid_t,heat.billet_t]
    for j,col in enumerate(['charge_t','liquid_t','billet_t']): residual('heat_to_clock_'+col,site[col],expected[:,j])
    residual('melt_mass',site.charge_t,site.liquid_t+site.melt_loss_t)
    residual('caster_mass',site.liquid_t,site.billet_t+site.cast_loss_t)
    residual('rolling_mass',site.rolled_billet_t,site.bar_t+site.rolling_loss_t)
    residual('caster_yield',site.billet_t,site.liquid_t*C['material']['cast_yield'])
    residual('rolling_yield',site.bar_t,site.rolled_billet_t*C['material']['rolling_yield'])
    opening=site.yard_stock_t.shift(1,fill_value=C['material']['initial_yard'])
    independently= C['material']['initial_yard']+np.cumsum(expected[:,2]-site.rolled_billet_t.to_numpy())
    residual('inventory_cumulative',site.yard_stock_t,independently)
    count('inventory_interval_end_bounds',site.yard_stock_t.between(0-TOL,C["material"]["yard_max"]+TOL))
    count('inventory_opening_minus_rolling_bounds',opening-site.rolled_billet_t>=-TOL)
    count('inventory_conservative_intraslot_upper',opening+site.billet_t<=C["material"]["yard_max"]+TOL)
    residual('whole_plant_mass',[C['material']['initial_yard']+site.charge_t.sum()],
             [site.bar_t.sum()+site.melt_loss_t.sum()+site.cast_loss_t.sum()+site.rolling_loss_t.sum()+site.yard_stock_t.iloc[-1]])
    rhf=wide['RHF_01']
    residual('coal_NCV_energy',rhf.fuel_input_GJ,rhf.fuel_kg*C['rhf']['coal_ncv']/1000)
    residual('coal_energy_components',rhf.fuel_input_GJ,rhf.fuel_base_GJ+rhf.fuel_fouling_GJ+rhf.fuel_holding_GJ)
    residual('RHF_baseline_fuel_from_bars',rhf.fuel_base_GJ,site.bar_t*C['rhf']['fuel_sec'])
    residual('RHF_fouling_fuel',rhf.fuel_fouling_GJ,rhf.fuel_base_GJ*C['faults']['fouling_loss']*rhf.latent_fouling)
    count('RHF_temperature_limits',rhf.loc[rhf.kW>0,'temp_C'].between(C['rhf']['temp_min'],C['rhf']['temp_max']))
    count('IF_tap_temperature_limits',h.tap_temp_C.between(C['if']['tap_min'],C['if']['tap_max']))
    count('heat_no_overlap',(h.start.iloc[1:].to_numpy()>=h.end.iloc[:-1].to_numpy()))
    residual('heat_wall_duration',(h.end-h.start).dt.total_seconds()/60,h.powered_min+h.nonpowered_min+h.outage_min)
    count('normal_IF_full_power',np.isclose(h.loc[~h.fault_label.str.contains('half'),'powered_min'],h.loc[~h.fault_label.str.contains('half'),'kWh']/C['if']['rated_kw']*60,atol=TOL,rtol=0))
    residual('half_power_duration',h.loc[h.fault_label.str.contains('half'),'powered_min'],h.loc[h.fault_label.str.contains('half'),'kWh']/C['if']['rated_kw']*60+C['faults']['half_minutes']*(1-C['faults']['half_fraction']))
    # Independently calculate repair availability from timestamped failure intervals.
    avail={}
    for asset in ['PMP_01','MILL_01']:
        failures=e[(e.asset_id==asset)&e.type.isin(('failure','preventive_service','preventive_restart'))]
        available=np.full(len(site),STEP,dtype=float)
        for r in failures.itertuples():
            begin=(r.start-START)/pd.Timedelta(minutes=1);end=(r.end-START)/pd.Timedelta(minutes=1)
            minute=np.arange(len(site))*STEP
            available-=np.maximum(0,np.minimum(minute+STEP,end)-np.maximum(minute,begin))
        avail[asset]=available
        residual('availability_'+asset,site['pump_available_min' if asset=='PMP_01' else 'mill_available_min'],available)
    count('rolling_RHF_and_mill_capacity',site.rolled_billet_t<=min(C['rhf']['capacity_tph'],C['mill']['capacity_tph'])*avail['MILL_01']/60+TOL)
    active=site.if_powered_min>0
    count('slot_cooling_interlock',(~active)|((wide['PMP_01'].kW>0)&(wide['PMP_01'].flow_m3_h>=C['pump']['min_flow'])&(site.if_powered_min<=avail['PMP_01']+TOL)))
    count('slot_average_contract_demand',site.kVA<=C["acceptance"]["contract_kva"]+TOL)
    for asset,kwmax in [('IF_01',5000),('MILL_01',1200),('PMP_01',75),('CMP_01',90)]:
        count('rated_power_'+asset,wide[asset].kW<=kwmax+TOL)
    rollhours=slots.hour+slots.minute/60
    window=work&(rollhours>=C['calendar']['mill_start_hour'])&(rollhours<C['calendar']['mill_start_hour']+C['calendar']['mill_hours'])
    count('rolling_outside_schedule',(site.rolled_billet_t<=TOL)|window)
    daily=site.groupby(day).agg(kWh=('kWh','sum'),billet_t=('billet_t','sum'),bar_t=('bar_t','sum'),liquid_t=('liquid_t','sum'))
    count('daily_billet_target',daily.loc[wd,'billet_t']>=C['material']['billet_target']-TOL)
    count('daily_bar_target',daily.loc[wd,'bar_t']>=C['material']['bar_target']-TOL)
    heatcounts=h.groupby(h.start.dt.normalize()).size().reindex(wd,fill_value=0)
    count('heats_per_working_day',heatcounts.between(12,13))
    # Compare independent per-shift aggregation with public production register.
    aggregation=site.assign(date=slots.strftime('%Y-%m-%d'),shift=(slots.hour//8).astype(str)).groupby(['date','shift'])
    pidx=p.set_index(['date','shift']).sort_index()
    for col in ['billet_t','bar_t','rolled_billet_t','liquid_t','charge_t','melt_loss_t','cast_loss_t','rolling_loss_t']:
        residual('production_register_'+col,pidx[col],aggregation[col].sum().reindex(pidx.index))
    residual('production_register_stock',pidx.yard_stock_t,aggregation.yard_stock_t.last().reindex(pidx.index))
    ifmwh=wide['IF_01'].loc[work,'kWh'].sum()/len(wd)/1000
    metrics=dict(if_sec=h.kWh.sum()/h.liquid_t.sum(),plant_MWh=daily.loc[wd,'kWh'].mean()/1000,
                 calendar_MWh=daily.kWh.mean()/1000,IF_share=wide['IF_01'].loc[work,'kWh'].sum()/site.loc[work,'kWh'].sum(),
                 slot_peak_kVA=site.kVA.max(),reported_peak_kVA=site.peak_kVA.max(),billet_tpd=daily.loc[wd,'billet_t'].mean(),
                 bar_tpd=daily.loc[wd,'bar_t'].mean(),liquid_tpd=daily.loc[wd,'liquid_t'].mean(),
                 inventory_min=site.yard_stock_t.min(),inventory_max=site.yard_stock_t.max(),intraslot_min_bound=(opening-site.rolled_billet_t).min(),
                 coal_tpd=rhf.loc[work,'fuel_kg'].sum()/len(wd)/1000,working_days=len(wd),heats=len(h),
                 total_electricity_kWh=site.kWh.sum(),total_charge_t=site.charge_t.sum(),total_liquid_t=site.liquid_t.sum(),
                 total_billet_t=site.billet_t.sum(),total_rolled_t=site.rolled_billet_t.sum(),total_bar_t=site.bar_t.sum(),
                 melt_loss_t=site.melt_loss_t.sum(),cast_loss_t=site.cast_loss_t.sum(),rolling_loss_t=site.rolling_loss_t.sum(),
                 ending_inventory=site.yard_stock_t.iloc[-1],coal_total_kg=rhf.fuel_kg.sum(),fuel_total_GJ=rhf.fuel_input_GJ.sum(),
                 violations=sum(checks.values()))
    counts=e.groupby(['asset_id','type','label']).size()
    metrics.update({'count_'+label:int(((h.fault_label.str.split('|')).map(lambda x:label in x)).sum()) for label in ['superheat','lid','charge_bad','half']})
    for asset in ['MILL_01','PMP_01']: metrics['failures_'+asset]=int(((e.asset_id==asset)&(e.type=='failure')).sum())
    segments=reconstruct_segments(h,e,config)
    recomputed=np.zeros(len(site));pmins=np.zeros(len(site));exactpeak=0.;peakseries=np.zeros(len(site));cooling_bad=0
    ifpieces=[[] for _ in range(len(site))]
    for a0,b0,power,heatid in segments:
        for i in range(max(0,int(a0//STEP)),min(len(site),int(np.ceil(b0/STEP)))):
            duration=max(0,min(b0,(i+1)*STEP)-max(a0,i*STEP))
            recomputed[i]+=power*duration/60;pmins[i]+=duration;ifpieces[i].append((a0,b0,power))
    residual('independent_IF_piecewise_energy',wide['IF_01'].kWh,recomputed)
    residual('independent_IF_powered_minutes',site.if_powered_min,pmins)
    badrepair={asset:[((r.start-START)/pd.Timedelta(minutes=1),(r.end-START)/pd.Timedelta(minutes=1)) for r in e[(e.asset_id==asset)&e.type.isin(('failure','preventive_service','preventive_restart'))].itertuples()] for asset in ['MILL_01','PMP_01']}
    pf=np.array([wide[x].pf.iloc[0] for x in ASSETS]);tan=np.sqrt(1/pf**2-1)
    vals=np.column_stack([wide[x].kW.to_numpy() for x in ASSETS])
    for i in range(len(site)):
        begin,end=i*STEP,(i+1)*STEP
        points={begin,end}
        for x,y,power in ifpieces[i]: points.update([max(begin,x),min(end,y)])
        for ints in badrepair.values():
            for x,y in ints:
                if x<end and y>begin: points.update([max(begin,x),min(end,y)])
        points=sorted(points)
        for left,right in zip(points[:-1],points[1:]):
            time=(left+right)/2
            power=vals[i].copy();power[0]=sum(k for x,y,k in ifpieces[i] if x<=time<y)
            for asset,j in [('MILL_01',2),('PMP_01',3)]:
                down=any(x<=time<y for x,y in badrepair[asset]);power[j]=0 if down else vals[i,j]*STEP/avail[asset][i] if avail[asset][i]>0 else 0
            demand=float(np.hypot(power.sum(),np.dot(power,tan)))
            peakseries[i]=max(peakseries[i],demand)
            if power[0]>0 and (power[3]<=0 or wide['PMP_01'].flow_m3_h.iloc[i]<C['pump']['min_flow']):cooling_bad+=1
    metrics['exact_piecewise_peak_kVA']=float(peakseries.max())
    checks['exact_piecewise_contract_demand']=int(np.sum(peakseries>C["acceptance"]["contract_kva"]+TOL))
    checks['exact_piecewise_pump_interlock']=cooling_bad
    count('published_peak_is_conservative',site.peak_kVA+TOL>=peakseries)
    metrics['violations']=sum(checks.values())
    metrics['daily_electricity_outside_5pct_count']=int(((daily.loc[wd,'kWh']/1000<96.9)|(daily.loc[wd,'kWh']/1000>107.1)).sum())
    metrics['run_mean_energy_in_envelope']=bool(96.9<=metrics['plant_MWh']<=107.1)
    if detail:
        assets={x:dict(MWh_working_day=wide[x].loc[work,'kWh'].sum()/len(wd)/1000,total_kWh=wide[x].kWh.sum(),
                      share_working=wide[x].loc[work,'kWh'].sum()/site.loc[work,'kWh'].sum()) for x in ASSETS}
        return metrics,checks,errors,assets,segments
    return metrics,checks,errors
