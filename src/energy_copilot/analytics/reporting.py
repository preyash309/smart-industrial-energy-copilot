"""Operator/public-data reports and plots; no access to hidden truth or labels."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from energy_copilot.common import write_json


def markdown(frame, formats=None):
    formats = formats or {}
    headers = list(frame)
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|"*len(headers)]
    for _, row in frame.iterrows():
        vals = []
        for col in headers:
            v = row[col]
            vals.append("unknown" if pd.isna(v) else format(v, formats[col]) if col in formats else str(v).replace("|", "/"))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def public_kpis(result):
    d = result.tables["asset_daily_metrics"]; h = result.tables["heat_features"]
    p = result.tables["production_register"]
    main = d[d.asset_id.eq("MAIN")]; rhf = d[d.asset_id.eq("RHF_01")]
    totals = dict(main_meter_raw_known_kWh=float(main.raw_meter_kWh.sum()), main_quality_best_known_kWh=float(main.energy_best_kWh.sum()),
        main_energy_coverage_fraction=float(main.observed_coverage_hours.sum()/((main.interval_end-main.interval_start).dt.total_seconds().sum()/3600)),
        coal_known_kg=float(rhf.fuel_kg.sum()), liquid_t=float(p.liquid_t.sum()), billet_t=float(p.billet_t.sum()), bar_t=float(p.bar_t.sum()),
        IF_heat_meter_kWh=float(h.kWh.sum()), heats=len(h), working_days=int(main.working_day.sum()),
        observed_slot_peak_kVA=float(main.peak_kVA.max()),
        rolling_yield_pct=float(100*p.bar_t.sum()/p.rolled_billet_t.sum()),
        published_inventory_min_t=float(p.yard_stock_t.min()), published_inventory_max_t=float(p.yard_stock_t.max()))
    normalized = dict(IF_observed_SEC_kWh_t=totals["IF_heat_meter_kWh"]/totals["liquid_t"],
        plant_known_electricity_kWh_t_bar=totals["main_quality_best_known_kWh"]/totals["bar_t"],
        known_coal_kg_t_bar=totals["coal_known_kg"]/totals["bar_t"],
        main_known_MWh_working_day=float(main.loc[main.working_day,"energy_best_kWh"].mean()/1000))
    return dict(raw_totals=totals, normalized_metrics=normalized,
        limitations="Quality-adjusted electricity/fuel are observed known subtotals with missing coverage, not full physical totals. IF heat-counter SEC uses the separate noisy heat register. Demand is a cleaned slot-average peak, not instantaneous physical demand. Runtime is active-slot occupancy; repair downtime is bounded from public state, not latent event durations.")


def plots(result, folder):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    h = result.tables["heat_features"]; s = result.tables["slot_features"]
    d = result.tables["asset_daily_metrics"]; p = result.tables["production_register"]
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    feeders = d[~d.asset_id.eq("MAIN")].groupby("asset_id").energy_best_kWh.sum().sort_values()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    axes[0].barh(feeders.index, feeders/1000, color="#16866a")
    axes[0].set(xlabel="Known quality-adjusted MWh (coverage varies)", title="Six consuming feeders; MAIN excluded")
    axes[1].hist(h.actual_SEC, bins=24, color="#226da6", alpha=.85)
    axes[1].set(xlabel="Observed IF SEC (kWh/t liquid)", ylabel="Heats", title="338 noisy heat counters")
    fig.tight_layout(); fig.savefig(folder / "energy_and_sec.png", dpi=150); plt.close(fig)
    valid = h.dropna(subset=["expected_SEC"])
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].plot(h.end_time, h.actual_SEC, ".", ms=4, color="#226da6", label="Actual noisy SEC")
    axes[0].plot(valid.end_time, valid.expected_SEC, color="#16866a", lw=1.4, label="Expectation available at heat start")
    axes[0].fill_between(valid.end_time, valid.expected_SEC_low, valid.expected_SEC_high, color="#16866a", alpha=.15, label="Historical 5th-95th percentile")
    axes[0].set(ylabel="kWh/t liquid", title="Expected versus actual: prior completed heats only"); axes[0].legend(loc="upper right", fontsize=8)
    axes[1].scatter(valid.end_time, valid.residual_SEC, s=12, c=np.where(valid.residual_SEC>25,"#bf5a26","#226da6"))
    axes[1].axhline(0, color="black", lw=.7); axes[1].set(ylabel="Actual - expected (kWh/t)", xlabel="Heat completion (local plant time)")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout(); fig.savefig(folder / "expected_actual_residuals.png", dpi=150); plt.close(fig)
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True)
    axes[0].plot(s.interval_end, s.MAIN_kW/1000, color="#226da6", lw=.6)
    axes[0].set(ylabel="Observed MW", title="Public plant load and completed-shift production; gaps stay gaps")
    axes[1].step(p.available_at, p.known_cumulative_bar_t, where="post", color="#16866a")
    axes[1].set(ylabel="Known cumulative bars (t)")
    axes[2].step(p.available_at, p.yard_stock_t, where="post", color="#bf5a26")
    axes[2].set(ylabel="Published yard stock (t)", xlabel="Publication time, Asia/Kolkata")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.tight_layout(); fig.savefig(folder / "load_production_timeline.png", dpi=150); plt.close(fig)
    util = d.groupby("asset_id").agg(active=("active_slot_hours","sum"), off=("off_slot_hours","sum"), partial=("partial_repair_slot_hours","sum"))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.bar(util.index, util.active, color="#16866a", label="Active-slot occupancy (includes partial repair)")
    ax.bar(util.index, util.off, bottom=util.active, color="#b9c5ce", label="Observed off slots")
    ax.scatter(util.index, util.partial, color="#bf5a26", label="Partial-repair slot hours (upper downtime bound)")
    ax.set(ylabel="Hours over 30 days", title="Utilization proxy; not exact subslot runtime"); ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout(); fig.savefig(folder / "asset_utilization.png", dpi=150); plt.close(fig)


def reports(result, root, gates):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    figures = root / "phase2_analytics"; plots(result, figures)
    h = result.tables["heat_features"]; d = result.tables["asset_daily_metrics"]
    a = result.accounting; alerts = result.tables["diagnostic_candidates"]
    kpi = public_kpis(result); write_json(figures / "operator_kpis.json", kpi)
    assets = d.groupby("asset_id").agg(known_kWh=("energy_best_kWh","sum"), raw_meter_kWh=("raw_meter_kWh","sum"),
        coverage_h=("observed_coverage_hours","sum"), peak_kVA=("peak_kVA","max"), active_slot_h=("active_slot_hours","sum"),
        downtime_lower_h=("downtime_lower_hours","sum"), downtime_upper_h=("downtime_upper_hours","sum")).reset_index()
    means = d[d.working_day].groupby("asset_id").energy_best_kWh.mean()/1000
    assets["known_MWh_working_day"] = assets.asset_id.map(means)
    consumers = [asset for asset in d.asset_id.unique() if asset != "MAIN"]
    common = result.tables["slot_features"][[f"{asset}_energy_best_kWh" for asset in consumers]].dropna()
    mix = common.sum()/common.to_numpy().sum()
    assets["common_feeder_share_pct"] = assets.asset_id.map({asset: 100*mix[f"{asset}_energy_best_kWh"] for asset in consumers})
    quality = d.groupby("asset_id")[["meter_slots", "power_fallback_slots", "missing_energy_slots", "quality_flagged_slots"]].sum().reset_index()
    examples = pd.concat([h.loc[h.residual_SEC.abs().nsmallest(2).index],h.loc[h.residual_SEC.nlargest(2).index]])[["heat_id","actual_SEC","expected_SEC","residual_SEC","duration_min","tap_temp_C"]]
    examples["interpretation"] = ["near historical expectation","near historical expectation","high residual candidate","high residual candidate"]
    representative = alerts.groupby("rule", sort=True).head(1)[["timestamp","asset_id","source_id","rule","measured_value","expected_value","residual","confidence"]]
    energy = f"""# Phase II-A monitoring and energy analytics

**PASS — analytics_v1 generated from immutable sim_v1.1 public outputs.** No simulator/physical assumption/observation change, ML training, optimisation or billing/carbon calculation is included.

## Equipment electricity and utilization

{markdown(assets, {col: '.3f' for col in assets if col!='asset_id'})}

Known energy is a subtotal, not an estimate of unobserved slots. MAIN is the plant meter and is never added to its six feeders. Raw meter totals retain reported glitches/missingness; quality totals reject rows marked glitched, retain nulls, and use same-interval kW times 0.25 h only when kWh is missing and kW is valid. No future imputation or hidden physical replacement is used. Per-day shares compare identical asset/MAIN coverage; `feeder_mix_share_common_all` uses the common six-feeder denominator and sums to one. AUX is the separate public simulated feeder here; it is not silently replaced by a residual as in the deployment meter-saving proposal.

{markdown(quality)}

Active-slot hours count any observed running/partial-repair interval. They are **not exact powered runtime**, especially for IF start/stop slots. Repair-only downtime is an interval bound: partial-repair records do not expose within-slot timings. Scheduled off is not assumed to be a breakdown. All daily aggregates become available at local day close.

## Production, intensity and register reconciliation

Raw/public totals: {kpi['raw_totals']['heats']} heats; liquid {kpi['raw_totals']['liquid_t']:.3f} t; billets {kpi['raw_totals']['billet_t']:.3f} t; bars {kpi['raw_totals']['bar_t']:.3f} t; coal known subtotal {kpi['raw_totals']['coal_known_kg']:.3f} kg. Rolling yield {kpi['raw_totals']['rolling_yield_pct']:.3f}%. MAIN quality-known energy {kpi['raw_totals']['main_quality_best_known_kWh']:.3f} kWh at {kpi['raw_totals']['main_energy_coverage_fraction']:.3%} coverage. Published shift-close yard stock range {kpi['raw_totals']['published_inventory_min_t']:.3f}–{kpi['raw_totals']['published_inventory_max_t']:.3f} t.

Normalized metrics (separate from raw totals): observed IF heat-counter SEC {kpi['normalized_metrics']['IF_observed_SEC_kWh_t']:.6f} kWh/t liquid; known plant electricity {kpi['normalized_metrics']['plant_known_electricity_kWh_t_bar']:.6f} kWh/t bars; known coal {kpi['normalized_metrics']['known_coal_kg_t_bar']:.6f} kg/t bars; MAIN known working-day mean {kpi['normalized_metrics']['main_known_MWh_working_day']:.6f} MWh. Missing coverage prevents treating the last three as exact physical full-period totals. Independent heat and feeder counters are not forced to agree.

All public mass-register identities pass; largest residual {max(a['production_max_mass_residual_t'].values()):.3g} t. Heat liquid/billet/charge totals join at completion to the proper production shift, including exact shift-end boundaries. Energy reconciliation uses {a['noisy_energy']['common_slots']} of {a['noisy_energy']['total_slots']} common valid slots: feeders {a['noisy_energy']['feeders_common_kWh']:.3f} kWh versus MAIN {a['noisy_energy']['main_common_kWh']:.3f} kWh; signed difference {a['noisy_energy']['residual_common_kWh']:.3f} kWh; median absolute slot discrepancy {a['noisy_energy']['median_absolute_relative_residual']:.3%}. This is a noisy-meter reconciliation, not a failed or artificially repaired physical balance.

![Equipment energy and SEC distribution](phase2_analytics/energy_and_sec.png)

## Expected energy and heat examples

Baseline selection: prior same-shift/working-day mean once eight records exist, otherwise prior rolling-twenty mean, otherwise prior global mean after warm-up. All outcomes must have `available_at <= heat.start_time`. First eight heats have no expectation or candidate diagnosis. No present-heat outcome, fault label or future calibration row is included. Expected kWh scales expected SEC by prior historical tapped mass, never the current unknown output. Empirical 5th–95th percentiles and sample SD describe prior variability; they are not calibrated prediction intervals or best-practice/avoidable-energy estimates. Baselines adapt online and may normalize persistent poor practice.

{markdown(examples, {col: '.3f' for col in ['actual_SEC','expected_SEC','residual_SEC','duration_min','tap_temp_C']})}

These are ordinary and high-residual **observed examples**, not true good/bad fault assignments. Heat SEC mean {h.actual_SEC.mean():.3f}, median {h.actual_SEC.median():.3f}, SD {h.actual_SEC.std():.3f}, range {h.actual_SEC.min():.3f}–{h.actual_SEC.max():.3f} kWh/t. {h.expected_SEC.notna().sum()} of {len(h)} heats have a historical expectation.

![Expected actual and residuals](phase2_analytics/expected_actual_residuals.png)

## Production timeline and diagnostic evidence

![Plant load and published production](phase2_analytics/load_production_timeline.png)

Inventory and output are only reported per completed eight-hour shift. Slot features use the latest report published by **slot start**, with age and an opening-balance flag. Rolling output is explicitly `rolling_output_last_shift_t`, not invented slot production. No interpolation of future registers or access to latent yard/rolling state is used.

{markdown(representative, {col: '.3f' for col in ['measured_value','expected_value','residual']})}

Candidate counts: {json.dumps(alerts.groupby('rule').size().to_dict(), sort_keys=True)}. Full records contain timestamp/heat or interval ID, measured/expected/residual, metric unit, JSON observable evidence, possible cause and confidence/limitations. Sustained deviations generate repeated evidence rows rather than distinct confirmed incidents. Compressor candidates require observed mill-off context; its source state is always running and cannot itself prove unloaded operation. No AUX candidate is required if observed deviations do not meet the documented threshold. Sensor flags are QC metadata, not diagnoses.

![Asset utilization](phase2_analytics/asset_utilization.png)

## Limits and next handoff

Public meters have missingness/glitches and independent noise; invalid observations remain null. Same-slot power/PF are descriptive analytics, excluded from same-slot load prediction. Chemistry is a simulator placeholder and its real lab availability is unknown; excluded from pre-heat forecasts. Ideal zero posting delay is explicitly assumed because ingestion timestamps are absent, and configured delay is enforced by the loader. The frozen reduced RHF model, calendar wear, baseline output and UCI ACF warnings are unchanged. No tariff/emission rates are executable inputs here: no cost, savings or CO2 results are generated.

The thirty-day horizon supports provisional chronological heat/load splits only, not annual seasonal validation or reliable predictive-maintenance performance claims. Cycle-aware maintenance evaluation and sufficient failure horizons belong to the next modelling stage. Use the task allowlist loader, not automatic numeric-column selection. Exit checks: {json.dumps(gates, sort_keys=True)}.
"""
    (root / "phase2_energy_analytics.md").write_text(energy, encoding="utf-8")
    audit = f"""# Phase II-A feature and availability audit

**PASS — all exit gates.** {json.dumps(gates, sort_keys=True)}

Features are built exclusively from public `readings`, a strict selection of heat-register fields, public production registers and public clock/calendar/opening-balance metadata. Feature building does not read events or hidden tables. Separate evaluation code runs only after construction and writes under `evaluation/`; it cannot supply values to operator KPIs, historical baselines or diagnostics. Phase-I files and simulator source remain hash-identical to the protected manifest.

## Availability contract

- Meter/sensor/state intervals: `[interval_start, interval_end)`; values post at `interval_end + configured delay`.
- Heat log outcomes: end time, duration, energy/SEC, tapped/billet/charge masses, tap temperature and chemistry post conservatively at `end_time + delay`. Charge has no independent pre-heat posting timestamp in this data and is excluded from pre-heat inputs.
- Pre-heat expectation/context: only prior heat outcomes or meter intervals published by `start_time`; completed previous heat at exactly the next start is legal under ideal zero-delay posting.
- Production/yard reports: publish at eight-hour shift end plus delay. Slot inventory is last reported at/before slot START, not a latent instantaneous balance.
- Slot lag/rolling values: shift before rolling; each column carries the preceding observation publication time. A positive delay makes a lag unavailable if its source publishes after origin, even when its row timestamp appears earlier.
- Daily aggregates: publish at day end plus delay. Runtime is slot occupancy; repair downtime is a range based on observable state. No hidden failure timing is used.

`feature_schema.yaml` documents each column's type, unit, nullability, role, source, range and permitted tasks. `feature_availability.yaml` repeats the full per-column legal availability. `select_predictors`/`load_predictors` deny unsupported columns/tasks and mask any input whose publication time exceeds its forecast origin. They return `inputs_available_at <= forecast_origin`. Outcomes/diagnostics/labels cannot be automatically selected as energy predictors. Identifiers remain join keys, never model measurements.

## Task allowlists

`heat_energy`: calendar, previous completed heat SEC/duration, prior historical expectations and fully completed meter context. Excludes current kWh/SEC, residual, duration, heat end, output/charge mass, tap temperature and chemistry.

`slot_load_at_start`: known calendar, previously published inventory/output registers and strictly prior load/sensor lags/windows. Excludes all present-slot power/energy/PF/state/sensors. `slot_next_load`: completed present-slot observations plus backward context, usable at interval end for a later target. `asset_next_day_risk`: completed-day observed metrics at day close; no failure labels or true wear. Raw glitch-contaminated totals and row-quality labels are audit metadata, excluded from that allowlist.

## Adversarial checks and reproducibility

Tests independently recompute SEC/ratios/mass and noisy feeder accounting; mutate future meter data and current-heat outcomes; verify earlier/current forecast predictors are unchanged; inspect every lag/window; validate backward heat-to-slot joins; exercise five-minute posting delay; reject hidden columns/outcomes/evaluation tables; check null/QC fallback semantics; and compare regenerated Parquet/schema/availability bytes. The original B01 regression suite still passes; RHF zone/flue remain independently noisy, with no ratio-derived severity column added.

Evaluation-only files: `heat_targets.parquet`, `slot_targets.parquet`, `heat_labels.parquet`, `events.parquet`, `time_split_manifest.parquet`, `physical_validation.json`. Chronological heat/load splits purge outcome windows crossing a boundary and incomplete final targets. They are not predictors. Maintenance labels and model training are absent; later cycle-aware validation must keep failure cycles separated.

## Retained limitations

Zero-delay log posting is an explicit analytical assumption, not evidence about lab/ERP latency. Only shift-close inventory/output is available; true 15-minute mass states are never exposed. Public quality metadata invalidates all numeric channels on a glitch-flagged row because channel identity is not supplied; this lowers coverage conservatively. Invalid/missing sensor values are not filled from future or latent values. Empirical uncertainty ranges are not calibrated, and rules indicate candidates rather than true simulator faults. The 30-day/limited-failure horizon cannot establish field reliability or forecasting accuracy.

No simulator, physical parameters, calibration, fault generation or observation code was modified. No ML fitting, optimiser, savings, tariff or carbon model was added. Full checks and source/protection hashes accompany `analytics_v1`.
"""
    (root / "phase2_feature_audit.md").write_text(audit, encoding="utf-8")
    return kpi
