"""Keep physical truth, known meter energy and predicted metrics distinguishable."""
import numpy as np
import pandas as pd


def realized_metrics(sim, inp, verifier):
    origin=pd.Timestamp(inp.forecast_origin);end=origin+pd.Timedelta(days=1)
    t=sim.latent_truth[(sim.latent_truth.timestamp>=origin)&(sim.latent_truth.timestamp<end)]
    site=t[t.asset_id.eq('MAIN')];h=sim.latent_heats[(sim.latent_heats.start>=origin)&(sim.latent_heats.start<end)]
    assets=t.groupby('asset_id').kWh.sum().to_dict(); rhf=t[t.asset_id.eq('RHF_01')]
    duration=(h.end-h.start).dt.total_seconds().sum()/3600
    repairs=sim.events[sim.events.type.eq('failure')]
    downtime={a:float(sum(max(pd.Timedelta(0),min(r.end,end)-max(r.start,origin)).total_seconds()/3600 for r in repairs[repairs.asset_id.eq(a)].itertuples())) for a in ('MILL_01','PMP_01')}
    readings=sim.readings[(sim.readings.asset_id=='MAIN')&(sim.readings.timestamp>=origin)&(sim.readings.timestamp<end)].sort_values('timestamp').reset_index(drop=True)
    rates=np.array([r.Rs_per_kWh for r in inp.tariff_calendar]);meter=readings.kWh
    good=np.isfinite(meter)&meter.ge(0)&~readings.sensor_glitch
    ledger=pd.DataFrame(dict(interval_start=readings.timestamp,tariff_Rs_per_kWh=rates,
        realized_raw_meter_kWh=meter,realized_QC_meter_kWh=meter.where(good),
        physical_evaluation_kWh=site.kWh.to_numpy(),meter_usable=good))
    for col in ('realized_raw_meter_kWh','realized_QC_meter_kWh','physical_evaluation_kWh'):
        ledger[col.replace('kWh','cost_Rs')]=ledger[col]*rates
    total=float(site.kWh.sum());bars=float(site.bar_t.sum());coal=float(rhf.fuel_kg.sum()/1000)
    m=dict(label='DIGITAL-TWIN-REALIZED',tariff_label='SYNTHETIC-TARIFF',physical_evaluation_only=True,
        liquid_t=float(site.liquid_t.sum()),billet_t=float(site.billet_t.sum()),bar_t=bars,
        total_kWh=total,MWh=total/1000,IF_kWh=float(assets['IF_01']),IF_SEC_kWh_per_t=float(h.kWh.sum()/h.liquid_t.sum()),
        plant_kWh_per_t_bars=total/bars,coal_t=coal,coal_t_per_t_bars=coal/bars,
        peak_average_kW=float(site.kW.max()),peak_average_kVA=float(site.kVA.max()),
        peak_piecewise_kVA=verifier['actual_day_peak_kVA'],demand_margin_kVA=inp.constraints.demand_limit_kVA-verifier['actual_day_peak_kVA'],
        inventory_min_t=float(site.yard_stock_t.min()),inventory_max_t=float(site.yard_stock_t.max()),final_inventory_t=float(site.yard_stock_t.iloc[-1]),
        IF_utilization=duration/24,IF_idle_hours=24-duration,IF_powered_hours=float(h.powered_min.sum()/60),
        rolling_utilization=float(site.rolled_billet_t.sum()/(inp.constraints.mill_capacity_tph*24)),
        asset_runtime_hours={a:float(g.kW.gt(0).sum()*.25) for a,g in t.groupby('asset_id')},asset_kWh=assets,
        downtime_hours=downtime,quality_flags=int((~h.chem_ok).sum()),constraint_violations=verifier['violations'],
        raw_known_meter_kWh=float(meter.sum()),QC_known_meter_kWh=float(meter.where(good).sum()),QC_meter_coverage=float(good.mean()),
        raw_known_meter_tariff_cost_Rs=float((meter*rates).sum()),QC_known_meter_tariff_cost_Rs=float((meter.where(good)*rates).sum()),
        physical_evaluation_tariff_cost_Rs=float(np.dot(site.kWh,rates)),
        cost_limitation='Raw/QC meter totals exclude missing readings; QC also excludes glitches. No truth filling. Complete physical cost is evaluation-only, not a meter bill.')
    return m,ledger


def paired_change(base, optimized):
    return dict(label='DIGITAL-TWIN-REALIZED',tariff_label='SYNTHETIC-TARIFF',
        kWh_reduction=base['total_kWh']-optimized['total_kWh'],
        kWh_reduction_pct=100*(base['total_kWh']-optimized['total_kWh'])/base['total_kWh'],
        physical_evaluation_cost_reduction_Rs=base['physical_evaluation_tariff_cost_Rs']-optimized['physical_evaluation_tariff_cost_Rs'],
        physical_evaluation_cost_reduction_pct=100*(base['physical_evaluation_tariff_cost_Rs']-optimized['physical_evaluation_tariff_cost_Rs'])/base['physical_evaluation_tariff_cost_Rs'],
        QC_known_meter_cost_difference_Rs=base['QC_known_meter_tariff_cost_Rs']-optimized['QC_known_meter_tariff_cost_Rs'],
        baseline_QC_coverage=base['QC_meter_coverage'],optimized_QC_coverage=optimized['QC_meter_coverage'],
        bar_t_change=optimized['bar_t']-base['bar_t'],production_equal=abs(optimized['bar_t']-base['bar_t'])<1e-8,
        baseline_kWh_per_t=base['plant_kWh_per_t_bars'],optimized_kWh_per_t=optimized['plant_kWh_per_t_bars'])

