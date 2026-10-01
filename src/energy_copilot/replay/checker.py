"""Evaluation-only physical accounting; no MILP expressions or simulator maths."""
import numpy as np
import pandas as pd
from energy_copilot.common import values
from scripts.independent_accounting import independent, reconstruct_segments, ASSETS


def exact_day_peaks(sim, origin, end):
    c=values(sim.config); start=pd.Timestamp(c['start']);step=c['clock_minutes']
    truth=sim.latent_truth; site=truth[truth.asset_id.eq('MAIN')].set_index('timestamp').loc[origin:end-pd.Timedelta(minutes=step)]
    wide={a:truth[truth.asset_id.eq(a)].set_index('timestamp').loc[site.index] for a in ASSETS}
    segments=reconstruct_segments(sim.latent_heats,sim.events,sim.config)
    repairs={a:[((r.start-start)/pd.Timedelta(minutes=1),(r.end-start)/pd.Timedelta(minutes=1))
                for r in sim.events[(sim.events.asset_id==a)&sim.events.type.eq('failure')].itertuples()] for a in ('PMP_01','MILL_01')}
    tan=np.array([np.sqrt(1/wide[a].pf.iloc[0]**2-1) for a in ASSETS]);peaks=[]
    for ts,row in site.iterrows():
        lo=(ts-start)/pd.Timedelta(minutes=1);hi=lo+step
        pieces=[s for s in segments if s[0]<hi and s[1]>lo];points={lo,hi}
        for a,b,_,_ in pieces: points.update((max(a,lo),min(b,hi)))
        for intervals in repairs.values():
            for a,b in intervals:
                if a<hi and b>lo:points.update((max(a,lo),min(b,hi)))
        points=sorted(points);peak=0.
        for left,right in zip(points[:-1],points[1:]):
            mid=(left+right)/2;p=np.array([wide[a].loc[ts,'kW'] for a in ASSETS])
            p[0]=sum(s[2] for s in pieces if s[0]<=mid<s[1])
            for a,j,field in [('MILL_01',2,'mill_available_min'),('PMP_01',3,'pump_available_min')]:
                down=any(x<=mid<y for x,y in repairs[a]);avail=row[field]
                p[j]=0. if down or avail<=0 else p[j]*step/avail
            peak=max(peak,float(np.hypot(p.sum(),p@tan)))
        peaks.append(peak)
    return np.array(peaks)


def verify_physics(sim, inp, controls=None):
    tables={n:getattr(sim,n) for n in ('latent_truth','latent_heats','events','production')}
    metrics,checks,errors=independent(tables,sim.config)
    origin=pd.Timestamp(inp.forecast_origin);end=origin+pd.Timedelta(days=1);c=values(sim.config)
    site=sim.latent_truth[(sim.latent_truth.asset_id=='MAIN')&(sim.latent_truth.timestamp>=origin)&(sim.latent_truth.timestamp<end)]
    heats=sim.latent_heats[(sim.latent_heats.start>=origin)&(sim.latent_heats.start<end)]
    peaks=exact_day_peaks(sim,origin,end);tol=c['acceptance']['tolerance']
    checks['replay_bar_order']=int(site.bar_t.sum()<inp.production_order.bars_t-tol)
    checks['replay_billet_order']=int(site.billet_t.sum()<inp.production_order.billets_t-tol)
    checks['replay_closing_reserve']=int(site.yard_stock_t.iloc[-1]<inp.production_order.final_inventory_min_t-tol)
    checks['replay_daily_demand']=int(np.count_nonzero(peaks>inp.constraints.demand_limit_kVA+tol))
    checks['replay_chemistry_flags']=int((~heats.chem_ok).sum())
    if controls is not None:
        actual=heats.set_index('heat_id')
        checks['replay_exact_heat_ids']=int(set(actual.index)!=set(controls.schedule)) if controls.schedule else 0
        checks['replay_exact_starts']=sum(abs((actual.loc[h,'start']-pd.Timestamp(t)).total_seconds())>1e-6 for h,t in controls.schedule.items())
        checks['replay_exact_rolling']=0
        for i,v in controls.rolling_dispatch.items():
            ts=pd.Timestamp(c['start'])+pd.Timedelta(minutes=i*c['clock_minutes'])
            true=sim.latent_truth[(sim.latent_truth.asset_id=='MAIN')&sim.latent_truth.timestamp.eq(ts)].rolled_billet_t.iloc[0]
            checks['replay_exact_rolling']+=int(abs(true-v)>tol)
    # Check all supplied availability/windows against actual physical operation.
    for a in inp.equipment_availability:
        rows=sim.latent_truth[(sim.latent_truth.asset_id==a)&(sim.latent_truth.timestamp>=origin)&(sim.latent_truth.timestamp<end)]
        masks=np.array(inp.equipment_availability[a])&np.array(inp.operating_windows[a])
        checks['replay_permissives_'+a]=int(np.count_nonzero((rows.kW.to_numpy()>tol)&~masks))
    return dict(label='DIGITAL-TWIN-REALIZED',feasible=not any(checks.values()),
                violations=sum(checks.values()),checks=checks,accounting_max_errors=errors,
                independent_full_run_metrics=metrics,actual_day_peak_kVA=float(peaks.max()),
                exact_day_peak_series=peaks.tolist(),method='independent ledger and piecewise demand reconstruction; hidden truth used ONLY for evaluation')

