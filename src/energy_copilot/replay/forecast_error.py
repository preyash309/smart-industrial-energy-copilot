"""Evaluation of unchanged origin-frozen predictions against replay outcomes."""
import numpy as np
import pandas as pd


def errors(actual, p50, p90=None):
    actual=np.asarray(actual,dtype=float);p50=np.asarray(p50,dtype=float)
    valid=np.isfinite(actual)&np.isfinite(p50);a=actual[valid];p=p50[valid]
    if not len(a):return dict(n=0,MAE=None,RMSE=None,bias_actual_minus_p50=None,p90_exceedance=None)
    out=dict(n=len(a),MAE=float(np.abs(a-p).mean()),RMSE=float(np.sqrt(np.mean((a-p)**2))),bias_actual_minus_p50=float((a-p).mean()))
    if p90 is not None:out['p90_exceedance']=float(np.mean(a>np.asarray(p90)[valid]))
    return out


def heat_comparison(result, heats):
    actual=heats.set_index('heat_id');rows=[]
    for row in result.schedule:
        if row['heat_id'] not in actual.index:continue
        h=actual.loc[row['heat_id']]
        rows.append(dict(heat_id=row['heat_id'],predicted_start=row['start'],actual_start=h.start,
            energy_p50_kWh=row['energy_p50_kWh'],energy_p90_kWh=row['energy_p90_kWh'],actual_energy_kWh=float(h.kWh),
            duration_p50_min=row['duration_p50_min'],duration_p90_min=row['duration_p90_min'],actual_duration_min=float((h.end-h.start)/pd.Timedelta(minutes=1)),
            actual_fault_labels=h.fault_label,evidence='DIGITAL-TWIN-REALIZED vs OPTIMIZER-PREDICTED; evaluation-only'))
    return pd.DataFrame(rows)


def compare_forecast(sim, inp, result, verifier):
    frame=heat_comparison(result,sim.latent_heats);origin=pd.Timestamp(inp.forecast_origin);end=origin+pd.Timedelta(days=1)
    select=(sim.latent_truth.timestamp>=origin)&(sim.latent_truth.timestamp<end)
    aux=sim.latent_truth[select&sim.latent_truth.asset_id.eq('AUX')];main=sim.latent_truth[select&sim.latent_truth.asset_id.eq('MAIN')]
    observed=sim.readings[(sim.readings.timestamp>=origin)&(sim.readings.timestamp<end)&sim.readings.asset_id.eq('AUX')].sort_values('timestamp')
    observed_values=observed.kW.where(~observed.sensor_glitch).to_numpy()
    loads=pd.DataFrame(dict(interval_start=main.timestamp,actual_AUX_kW=aux.kW.to_numpy(),observed_QC_AUX_kW=observed_values,
        AUX_p50_kW=[p.load_p50_kW for p in inp.background_load_forecast],AUX_p90_kW=[p.load_p90_kW for p in inp.background_load_forecast],
        actual_MAIN_kW=main.kW.to_numpy(),predicted_selected_MAIN_kW=[r['total_kW'] for r in result.load_trajectory],
        actual_average_kVA=main.kVA.to_numpy(),actual_piecewise_kVA=verifier['exact_day_peak_series'],
        predicted_average_kVA=[r['average_kVA'] for r in result.load_trajectory],predicted_kVA_bound=[r['kVA_bound'] for r in result.load_trajectory]))
    summary=dict(heat_energy=errors(frame.actual_energy_kWh,frame.energy_p50_kWh,frame.energy_p90_kWh),
        heat_duration=errors(frame.actual_duration_min,frame.duration_p50_min,frame.duration_p90_min),
        AUX_physical=errors(loads.actual_AUX_kW,loads.AUX_p50_kW,loads.AUX_p90_kW),
        AUX_observed_QC=errors(loads.observed_QC_AUX_kW,loads.AUX_p50_kW,loads.AUX_p90_kW),
        MAIN_selected_mode=errors(loads.actual_MAIN_kW,loads.predicted_selected_MAIN_kW),
        peak_bound_error_actual_minus_predicted=verifier['actual_day_peak_kVA']-result.predicted_metrics['predicted_peak_kVA_bound'],
        schedule_domain='origin-frozen stale context and shifted starts; never update predictions with realized intervening heats')
    return summary,frame,loads

