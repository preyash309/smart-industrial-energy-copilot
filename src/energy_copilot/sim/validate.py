"""Independent output-ledger validation; freezes require every gate to pass."""
from __future__ import annotations
import numpy as np
import pandas as pd
from energy_copilot.common import values
from .engine import InvariantError


def validate_simulation(result, baseline=True):
    c=values(result.config);m=c["material"];a=c["acceptance"];step=c["clock_minutes"]
    truth=result.latent_truth;h=result.latent_heats
    site=truth[truth.asset_id.eq("MAIN")].set_index("timestamp")
    assets=truth[~truth.asset_id.eq("MAIN")]
    tol=a["tolerance"];checks={}
    def check(name,condition):
        checks[name]=bool(condition)
        if not condition:
            raise InvariantError(f"Validation gate failed: {name}")
    check("shared_clock",site.index.is_unique and site.index.to_series().diff().dropna().eq(pd.Timedelta(minutes=step)).all()
          and truth.groupby("timestamp").size().eq(7).all())
    summed=assets.groupby("timestamp").kWh.sum().reindex(site.index)
    check("electrical_balance",np.allclose(summed,site.kWh,atol=tol,rtol=0))
    check("power_energy_units",np.allclose(truth.kW*step/60,truth.kWh,atol=tol,rtol=0))
    check("feeder_apparent_power",np.allclose(assets.kW/assets.pf,assets.kVA,atol=tol,rtol=0))
    reactive=assets.assign(q=assets.kW*np.tan(np.arccos(assets.pf))).groupby("timestamp").q.sum().reindex(site.index)
    check("main_vector_power",np.allclose(np.hypot(site.kW,reactive),site.kVA,atol=tol,rtol=0))
    if_sum=truth.loc[truth.asset_id.eq("IF_01"),"kWh"].sum()
    check("furnace_heat_meter_balance",abs(if_sum-h.kWh.sum())<tol)
    check("furnace_loss_accounting",np.allclose(h.kWh,h.best_kWh+h.practice_kWh+h.fault_kWh,atol=tol,rtol=0))
    check("furnace_cycle_consistency",np.allclose((h.end-h.start).dt.total_seconds()/60,h.powered_min+h.nonpowered_min+h.outage_min,atol=tol,rtol=0))
    normal=h[~h.fault_label.str.contains("half",na=False)]
    check("full_power_duration",np.allclose(normal.powered_min,normal.kWh/c["if"]["rated_kw"]*60,atol=tol,rtol=0))
    check("heat_no_overlap",len(h)<2 or (h.start.iloc[1:].to_numpy()>=h.end.iloc[:-1].to_numpy()).all())
    check("melt_balance",np.allclose(site.charge_t,site.liquid_t+site.melt_loss_t,atol=tol,rtol=0))
    check("cast_balance",np.allclose(site.liquid_t,site.billet_t+site.cast_loss_t,atol=tol,rtol=0))
    check("rolling_balance",np.allclose(site.rolled_billet_t,site.bar_t+site.rolling_loss_t,atol=tol,rtol=0))
    check("caster_yield",np.allclose(site.billet_t,site.liquid_t*m["cast_yield"],atol=tol,rtol=0))
    check("rolling_yield",np.allclose(site.bar_t,site.rolled_billet_t*m["rolling_yield"],atol=tol,rtol=0))
    previous=site.yard_stock_t.shift(1,fill_value=m["initial_yard"])
    check("yard_balance",np.allclose(previous+site.billet_t-site.rolled_billet_t,site.yard_stock_t,atol=tol,rtol=0))
    check("inventory_bounds",site.yard_stock_t.between(m["yard_min"]-tol,m["yard_max"]+tol).all())
    check("rolling_capacity",(site.rolled_billet_t<=min(c["mill"]["capacity_tph"],c["rhf"]["capacity_tph"])*site.mill_available_min/60+tol).all())
    check("demand",(site.peak_kVA<=a["contract_kva"]+tol).all() and (site.kVA<=a["contract_kva"]+tol).all())
    pump=truth[truth.asset_id.eq("PMP_01")].set_index("timestamp")
    powered=site.if_powered_min>0
    check("pump_interlock",(site.if_powered_min<=site.pump_available_min+tol).all()
          and (pump.loc[powered,"flow_m3_h"]>=c["pump"]["min_flow"]).all() and (pump.loc[powered,"kW"]>0).all())
    rhf=truth[truth.asset_id.eq("RHF_01")]
    check("fuel_energy_balance",np.allclose(rhf.fuel_input_GJ,rhf.fuel_base_GJ+rhf.fuel_fouling_GJ+rhf.fuel_holding_GJ,atol=tol,rtol=0)
          and np.allclose(rhf.fuel_kg*c["rhf"]["coal_ncv"]/1000,rhf.fuel_input_GJ,atol=tol,rtol=0))
    active=rhf.kW>0
    check("rhf_temperature",rhf.loc[active,"temp_C"].between(c["rhf"]["temp_min"],c["rhf"]["temp_max"]).all())
    check("tap_temperature",h.tap_temp_C.between(c["if"]["tap_min"],c["if"]["tap_max"]).all())
    check("latent_boundary",not any(col.startswith("latent_") for col in result.readings.columns)
          and not {"powered_min","outage_min","fault_kWh"}&set(result.heats.columns))
    daily=site.groupby(site.index.normalize()).agg(kWh=("kWh","sum"),bar_t=("bar_t","sum"),billet_t=("billet_t","sum"),
                 working_day=("working_day","max"),peak_kVA=("peak_kVA","max"))
    wd=daily[daily.working_day]
    ifdaily=truth[truth.asset_id.eq("IF_01")].groupby(truth[truth.asset_id.eq("IF_01")].timestamp.dt.normalize()).kWh.sum()
    coaldaily=rhf.groupby(rhf.timestamp.dt.normalize()).fuel_kg.sum()/1000
    counts=h.groupby(h.start.dt.normalize()).size().reindex(wd.index,fill_value=0) if len(h) else pd.Series(0,index=wd.index)
    check("daily_billet_target",(wd.billet_t>=m["billet_target"]-tol).all())
    check("daily_bar_target",(wd.bar_t>=m["bar_target"]-tol).all())
    mean_sec=float(h.kWh.sum()/h.liquid_t.sum()) if len(h) else None
    summary=dict(checks=checks,baseline=baseline,seed=result.scenario_manifest["seed"],days=len(daily),working_days=len(wd),heats=len(h),
                 mean_if_sec_kWh_t=mean_sec,heats_per_working_day=float(counts.mean()) if len(wd) else None,
                 mean_working_day_MWh=float(wd.kWh.mean()/1000) if len(wd) else None,
                 mean_calendar_day_MWh=float(daily.kWh.mean()/1000),
                 if_working_day_share=float(ifdaily.reindex(wd.index).sum()/wd.kWh.sum()) if len(wd) else None,
                 mean_coal_t_working_day=float(coaldaily.reindex(wd.index).mean()) if len(wd) else None,
                 mean_billet_t_working_day=float(wd.billet_t.mean()) if len(wd) else None,
                 mean_bar_t_working_day=float(wd.bar_t.mean()) if len(wd) else None,
                 peak_kVA=float(site.peak_kVA.max()),min_yard_t=float(site.yard_stock_t.min()),max_yard_t=float(site.yard_stock_t.max()),
                 total_electricity_kWh=float(site.kWh.sum()),total_coal_kg=float(rhf.fuel_kg.sum()),
                 total_bar_t=float(site.bar_t.sum()),electrical_balance_max_error_kWh=float(abs(summed-site.kWh).max()),
                 event_counts=result.events.groupby(["asset_id","type","label"]).size().rename("count").reset_index().to_dict("records"))
    if baseline and len(wd):
        for name,value,key in [("baseline_sec",mean_sec,"sec_range"),("baseline_electricity",summary["mean_working_day_MWh"],"daily_mwh"),
                               ("baseline_if_share",summary["if_working_day_share"],"if_share"),("baseline_coal",summary["mean_coal_t_working_day"],"coal_tpd")]:
            lo,hi=a[key];check(name,lo<=value<=hi)
        check("baseline_heat_count",counts.between(12,13).all())
    summary["checks"]=checks
    return summary
