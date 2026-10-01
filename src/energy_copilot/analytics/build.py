"""Public-only Phase-II-A analytics; no simulator or hidden table imports."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import pandas as pd
import yaml

from energy_copilot.common import ROOT, values, validate_parameters
from energy_copilot.schema import ALLOWED_OBS_FEATURES, UNITS, validate_table
from .contracts import Contracts, field
from .baselines import heat_history

HEAT_INPUTS = ("heat_id", "asset_id", "start", "end", "charge_t", "liquid_t", "billet_t", "kWh", "tap_temp_C", "chem_ok")
PRODUCTION_INPUTS = ("plant_id", "date", "shift", "billet_t", "bar_t", "rolled_billet_t", "yard_stock_t", "liquid_t", "charge_t", "melt_loss_t", "cast_loss_t", "rolling_loss_t", "rolling_yield_pct")


@dataclass
class PublicInputs:
    readings: pd.DataFrame
    heats: pd.DataFrame
    production: pd.DataFrame
    settings: dict


def load_public_inputs(directory):
    directory = Path(directory)
    schema = yaml.safe_load((directory / "schema.yaml").read_text())
    readings = pd.read_parquet(directory / "readings.parquet")
    heats = pd.read_parquet(directory / "heats.parquet")
    production = pd.read_parquet(directory / "production.parquet")
    for name, frame in (("readings", readings), ("heats", heats), ("production", production)):
        validate_table(frame, name, schema)
    cfg = yaml.safe_load((directory / "config_snapshot.yaml").read_text())
    # Explicitly restrict metadata to public calendar/clock/opening-balance settings.
    settings = dict(clock_minutes=cfg["clock_minutes"]["value"], timezone=cfg["timezone"], start=cfg["start"],
                    calendar=values(cfg["calendar"]), initial_yard=cfg["material"]["initial_yard"]["value"])
    return PublicInputs(readings, heats[list(HEAT_INPUTS)].copy(), production[list(PRODUCTION_INPUTS)].copy(), settings)


def working_day(times, settings):
    x = pd.to_datetime(times)
    return ~(x.dt.dayofweek.isin(settings["calendar"]["off_weekdays"])
             | x.dt.strftime("%Y-%m-%d").isin(settings["calendar"]["maintenance_dates"]))


def clean_readings(inputs, parameters):
    r = inputs.readings.copy()
    r["timestamp"] = r.timestamp.astype("datetime64[ns]")
    r["interval_start"] = r.timestamp
    r["interval_end"] = r.timestamp + pd.Timedelta(minutes=inputs.settings["clock_minutes"])
    r["available_at"] = r.interval_end + pd.Timedelta(minutes=parameters["publication_delay_minutes"])
    raw_energy = r.kWh.copy()
    # Public quality flags are QC metadata, never predictor columns. A row-level
    # glitch has no channel identity: conservatively invalidate all numeric sensors.
    numeric = [col for col in ALLOWED_OBS_FEATURES if col not in ("state", "tariff_band")]
    for col in numeric:
        x = r[col].where(np.isfinite(r[col]) & ~r.sensor_glitch)
        if col == "pf": x = x.where(x.between(0, 1))
        elif col not in ("temp_C", "flue_temp_C"): x = x.where(x.ge(0))
        r[col] = x
    dt = inputs.settings["clock_minutes"]/60
    r["raw_meter_kWh"] = raw_energy
    r["energy_best_kWh"] = r.kWh.combine_first(r.kW*dt)
    r["energy_method"] = np.select([r.kWh.notna(), r.kW.notna()], ["meter", "same_interval_power"], default="missing")
    r["quality_flagged"] = inputs.readings.sensor_glitch
    return r


def production_register(inputs, parameters):
    p = inputs.production[list(PRODUCTION_INPUTS)].copy()
    width = pd.Timedelta(hours=parameters["shift_hours"])
    p["interval_start"] = (pd.to_datetime(p.date) + pd.to_timedelta(p["shift"].astype(int)*parameters["shift_hours"], unit="h")).astype("datetime64[ns]")
    p["interval_end"] = p.interval_start + width
    p["available_at"] = p.interval_end + pd.Timedelta(minutes=parameters["publication_delay_minutes"])
    p = p.sort_values("interval_start").reset_index(drop=True)
    p["known_cumulative_bar_t"] = p.bar_t.cumsum()
    p["working_day"] = working_day(p.interval_start, inputs.settings)
    return p


def slot_table(clean, production, inputs, config):
    par = config["parameters"]; slots = pd.DataFrame({"interval_start": sorted(clean.timestamp.unique())})
    slots["timestamp"] = slots.interval_start
    slots["interval_end"] = slots.interval_start + pd.Timedelta(minutes=inputs.settings["clock_minutes"])
    slots["available_at"] = slots.interval_end + pd.Timedelta(minutes=par["publication_delay_minutes"])
    fields = {col: field("local datetime", "interval_start" if col in ("timestamp", "interval_start") else "available_at", "metadata") for col in slots}
    start_tasks = ("slot_load_at_start", "slot_next_load")
    end_tasks = ("slot_next_load",)
    for name, series in (("hour", slots.interval_start.dt.hour), ("weekday", slots.interval_start.dt.dayofweek),
                         ("shift", slots.interval_start.dt.hour//par["shift_hours"]),
                         ("working_day", working_day(slots.interval_start, inputs.settings))):
        slots[name] = series; fields[name] = field("calendar", "interval_start", "calendar", start_tasks)
    channel_data = {}
    for asset in config["assets"]:
        r = clean.loc[clean.asset_id.eq(asset)].set_index("timestamp").reindex(slots.interval_start)
        for col in [*ALLOWED_OBS_FEATURES, "energy_best_kWh", "energy_method"]:
            name = f"{asset}_{col}"; channel_data[name] = r[col].to_numpy()
            fields[name] = field(UNITS.get(col, "kWh" if col == "energy_best_kWh" else "category"), "available_at",
                "quality_metadata" if col == "energy_method" else "observed", () if col == "energy_method" else end_tasks,
                source=f"readings.{col}; public QC" if col not in ALLOWED_OBS_FEATURES else f"readings.{col}")
    slots = pd.concat([slots, pd.DataFrame(channel_data, index=slots.index)], axis=1).copy()
    published = production[["available_at", "yard_stock_t", "bar_t", "rolling_yield_pct", "known_cumulative_bar_t"]].rename(columns={
        "available_at": "production_report_available_at", "yard_stock_t": "billet_inventory_t", "bar_t": "rolling_output_last_shift_t"})
    slots = pd.merge_asof(slots.sort_values("interval_start"), published.sort_values("production_report_available_at"),
                          left_on="interval_start", right_on="production_report_available_at", direction="backward").copy()
    slots["inventory_is_opening_balance"] = slots.production_report_available_at.isna()
    slots["billet_inventory_t"] = slots.billet_inventory_t.fillna(inputs.settings["initial_yard"])
    slots["production_report_available_at"] = slots.production_report_available_at.fillna(pd.Timestamp(inputs.settings["start"]))
    slots["known_cumulative_bar_t"] = slots.known_cumulative_bar_t.fillna(0.)
    slots["inventory_age_min"] = (slots.interval_start-slots.production_report_available_at).dt.total_seconds()/60
    for col in ("production_report_available_at", "billet_inventory_t", "rolling_output_last_shift_t", "rolling_yield_pct", "known_cumulative_bar_t", "inventory_is_opening_balance", "inventory_age_min"):
        fields[col] = field("local datetime" if col.endswith("available_at") else "min" if col.endswith("_min") else "percent" if col.endswith("pct") else "boolean" if col.startswith("inventory_is") else "t",
            "interval_start" if col.endswith("_min") or col.startswith("inventory_is") else "production_report_available_at", "published_register", start_tasks,
            source="production completed-shift register / configured opening balance", notes="Last published value; not true instantaneous stock/output.")
    lag_sources = ("MAIN_kW", "MAIN_kWh", "MAIN_kVA", "IF_01_kWh", "MILL_01_vibration_mm_s", "PMP_01_vibration_mm_s")
    # When a nonzero posting delay is configured, do not claim delayed preceding
    # meters were known at interval start. Publish explicit window availability.
    slots["history_available_at"] = slots.available_at.shift(1)
    fields["history_available_at"] = field("local datetime", "history_available_at", "metadata")
    for col in lag_sources:
        for lag in par["slot_lags"]:
            name = f"{col}_lag_{lag}"; at = f"lag_{lag}_available_at"
            slots[name] = slots[col].shift(lag)
            slots[at] = slots.available_at.shift(lag)
            fields[at] = field("local datetime", at, "metadata")
            fields[name] = field(fields[col]["unit"], at, "past_observation", start_tasks, source=f"{col}.shift({lag})")
        for window in par["slot_windows"]:
            previous = slots[col].shift(1).rolling(window, min_periods=1)
            for suffix, series in (("mean", previous.mean()), ("count", previous.count())):
                name = f"{col}_past_{window}_{suffix}"; slots[name] = series
                fields[name] = field(fields[col]["unit"] if suffix == "mean" else "sample", "history_available_at", "past_observation", start_tasks, source=f"{col}.shift(1).rolling({window})")
    return slots, fields


def heat_table(inputs, slots, config):
    par = config["parameters"]; h = inputs.heats[list(HEAT_INPUTS)].copy().rename(columns={"start": "start_time", "end": "end_time"})
    h = h.sort_values(["start_time", "heat_id"]).reset_index(drop=True)
    h["available_at"] = h.end_time + pd.Timedelta(minutes=par["publication_delay_minutes"])
    h["duration_min"] = (h.end_time-h.start_time).dt.total_seconds()/60
    h["SEC_kWh_per_t"] = h.kWh/h.liquid_t.where(h.liquid_t.gt(0)); h["actual_SEC"] = h.SEC_kWh_per_t
    h["hour"] = h.start_time.dt.hour; h["weekday"] = h.start_time.dt.dayofweek
    h["shift"] = h.start_time.dt.hour//par["shift_hours"]; h["working_day"] = working_day(h.start_time, inputs.settings)
    h = pd.concat([h, heat_history(h, par)], axis=1)
    h["residual_SEC"] = h.actual_SEC-h.expected_SEC
    context_cols = ("MAIN_kW", "MAIN_kVA", "IF_01_kW", "RHF_01_temp_C", "PMP_01_flow_m3_h", "MILL_01_vibration_mm_s")
    context = slots[["available_at", *context_cols]].rename(columns={"available_at": "context_available_at", **{col: f"context_{col}" for col in context_cols}})
    h = pd.merge_asof(h.sort_values("start_time"), context.sort_values("context_available_at"), left_on="start_time", right_on="context_available_at", direction="backward")
    h["context_age_min"] = (h.start_time-h.context_available_at).dt.total_seconds()/60
    fields = {}
    calendar = {"start_time", "hour", "weekday", "shift", "working_day"}
    historical = {"previous_heat_SEC", "previous_heat_duration", "history_count", "global_mean_SEC", "shift_mean_SEC", "rolling_mean_SEC", "historical_duration_mean", "historical_duration_sd", "expected_SEC", "expected_SEC_sd", "expected_SEC_low", "expected_SEC_high", "expected_n", "expected_method", "expected_liquid_t", "expected_kWh"}
    for col in h:
        unit = "kWh/t liquid" if "SEC" in col else "kWh" if col.endswith("kWh") else "min" if "duration" in col or col.endswith("_min") else "t" if col.endswith("_t") else UNITS.get(col, "local datetime" if pd.api.types.is_datetime64_any_dtype(h[col]) else "identifier or category" if col in ("heat_id", "asset_id", "expected_method") else "dimensionless")
        if col in ("heat_id", "asset_id"):
            fields[col] = field(unit, "start_time", "metadata")
        elif col in calendar or col in historical:
            fields[col] = field(unit, "start_time", "calendar" if col in calendar else "historical_baseline", ("heat_energy",),
                source="completed heat logs with available_at <= current heat start" if col in historical else "known calendar")
        elif col.startswith("context_") and col not in ("context_available_at", "context_age_min"):
            source_col = col.removeprefix("context_")
            fields[col] = field(next((UNITS[x] for x in UNITS if source_col.endswith("_"+x)), unit), "context_available_at", "past_observation", ("heat_energy",), source="latest fully published meter interval before heat start")
        elif col == "context_age_min":
            fields[col] = field("min", "start_time", "past_observation", ("heat_energy",))
        else:
            fields[col] = field(unit, "available_at", "metadata" if col.endswith("available_at") else "outcome_or_completed_register", source="completed public heat log; excluded from pre-heat forecasts")
    return h, fields


def asset_daily(clean, production, inputs, config):
    dt = inputs.settings["clock_minutes"]/60; par = config["parameters"]
    r = clean.assign(date=clean.timestamp.dt.normalize())
    rows = []
    for (asset, day), g in r.groupby(["asset_id", "date"], sort=True):
        source = production[production.interval_start.dt.normalize().eq(day)]
        row = dict(asset_id=asset, date=day, interval_start=day, interval_end=day+pd.Timedelta(days=1),
            available_at=day+pd.Timedelta(days=1, minutes=par["publication_delay_minutes"]),
            working_day=bool(working_day(pd.Series([day]), inputs.settings).iloc[0]),
            raw_meter_kWh=g.raw_meter_kWh.sum(min_count=1), valid_meter_kWh=g.kWh.sum(min_count=1),
            energy_best_kWh=g.energy_best_kWh.sum(min_count=1), mean_kW=g.kW.mean(), peak_kW=g.kW.max(), peak_kVA=g.kVA.max(),
            mean_pf=g.pf.mean(), fuel_kg=g.fuel_kg.sum(min_count=1),
            valid_energy_slots=int(g.energy_best_kWh.notna().sum()), meter_slots=int(g.kWh.notna().sum()),
            power_fallback_slots=int(g.energy_method.eq("same_interval_power").sum()), missing_energy_slots=int(g.energy_best_kWh.isna().sum()),
            quality_flagged_slots=int(g.quality_flagged.sum()), observed_coverage_hours=g.energy_best_kWh.notna().sum()*dt,
            active_slot_hours=g.state.isin(["running", "repair_partial"]).sum()*dt,
            off_slot_hours=g.state.eq("off").sum()*dt, partial_repair_slot_hours=g.state.eq("repair_partial").sum()*dt,
            downtime_lower_hours=g.state.eq("repair").sum()*dt,
            downtime_upper_hours=g.state.isin(["repair", "repair_partial"]).sum()*dt,
            utilization_slot_fraction=g.state.isin(["running", "repair_partial"]).mean(),
            bar_t=source.bar_t.sum(), billet_t=source.billet_t.sum(), liquid_t=source.liquid_t.sum(),
            rolling_yield_pct=100*source.bar_t.sum()/source.rolled_billet_t.sum() if source.rolled_billet_t.sum()>0 else np.nan)
        row["electricity_kWh_per_t_bar"] = row["energy_best_kWh"]/row["bar_t"] if row["bar_t"]>0 else np.nan
        row["fuel_kg_per_t_bar"] = row["fuel_kg"]/row["bar_t"] if row["bar_t"]>0 else np.nan
        for col in ("temp_C", "vibration_mm_s", "flow_m3_h", "pressure_bar", "rpm"):
            row[f"mean_{col}"] = g[col].mean(); row[f"max_{col}"] = g[col].max()
        rows.append(row)
    daily = pd.DataFrame(rows)
    main = r.loc[r.asset_id.eq("MAIN"), ["timestamp", "energy_best_kWh"]].set_index("timestamp").energy_best_kWh
    common = r.pivot(index="timestamp", columns="asset_id", values="energy_best_kWh").dropna()
    for i, row in daily.iterrows():
        asset = r.loc[r.asset_id.eq(row.asset_id) & r.date.eq(row.date)].set_index("timestamp").energy_best_kWh
        pair = pd.concat([asset.rename("asset"), main.rename("main")], axis=1, sort=True).dropna()
        matched = common.loc[common.index.normalize()==row.date]
        daily.loc[i, "asset_share_MAIN_common"] = pair.asset.sum()/pair.main.sum() if pair.main.sum()>0 else np.nan
        denom = matched.drop(columns="MAIN").to_numpy().sum()
        daily.loc[i, "feeder_mix_share_common_all"] = matched[row.asset_id].sum()/denom if row.asset_id != "MAIN" and denom>0 else np.nan
    for col in ("mean_temp_C", "mean_vibration_mm_s"):
        daily[f"{col}_past_7d_mean"] = daily.groupby("asset_id")[col].transform(lambda x: x.shift(1).rolling(par["asset_history_days"], min_periods=1).mean())
    fields = {}
    for col in daily:
        unit = "kWh/t bar" if col.endswith("kWh_per_t_bar") else "kg/t bar" if col.endswith("kg_per_t_bar") else "kWh" if "kWh" in col else "h (interval proxy/bound)" if col.endswith("hours") else "kVA" if col.endswith("kVA") else "kW" if col.endswith("kW") else "t" if col.endswith("_t") else "kg coal" if col == "fuel_kg" else "percent" if col.endswith("pct") else next((UNITS[x] for x in UNITS if x in col), "local datetime" if pd.api.types.is_datetime64_any_dtype(daily[col]) else "dimensionless")
        metadata = col in ("asset_id", "date", "interval_start", "interval_end", "available_at", "raw_meter_kWh", "quality_flagged_slots")
        fields[col] = field(unit, "available_at", "metadata_or_quality_audit" if metadata else "completed_day_metric",
                            () if metadata else ("asset_next_day_risk",), source="clean public meters/states and completed production registers")
    return daily, fields


def accounting_checks(clean, inputs, config):
    par = config["parameters"]; p = inputs.production.sort_values(["date", "shift"]).reset_index(drop=True)
    previous = p.yard_stock_t.shift(1, fill_value=inputs.settings["initial_yard"])
    mass = {"melt": (p.charge_t-p.liquid_t-p.melt_loss_t).abs().max(),
            "cast": (p.liquid_t-p.billet_t-p.cast_loss_t).abs().max(),
            "rolling": (p.rolled_billet_t-p.bar_t-p.rolling_loss_t).abs().max(),
            "yard": (previous+p.billet_t-p.rolled_billet_t-p.yard_stock_t).abs().max()}
    assert all(error <= par["register_tolerance"] for error in mass.values()), mass
    # Heat belongs to the shift where its output completes, including exact ends.
    h = inputs.heats.copy(); completion = h.end-pd.Timedelta(nanoseconds=1)
    h["date"] = completion.dt.strftime("%Y-%m-%d"); h["shift"] = (completion.dt.hour//par["shift_hours"]).astype(str)
    per_heat = h.groupby(["date", "shift"])[["liquid_t", "billet_t", "charge_t"]].sum()
    per_shift = p.set_index(["date", "shift"])
    heat_errors = {col: float((per_heat[col].reindex(per_shift.index, fill_value=0)-per_shift[col]).abs().max()) for col in per_heat}
    assert all(x <= par["register_tolerance"] for x in heat_errors.values())
    wide = clean.pivot(index="timestamp", columns="asset_id", values="energy_best_kWh")
    common = wide.dropna()
    feeders = common.drop(columns="MAIN").sum(axis=1)
    residual = feeders-common.MAIN
    rel = residual.abs()/common.MAIN.where(common.MAIN.gt(0))
    energy = dict(common_slots=len(common), total_slots=len(wide), main_common_kWh=float(common.MAIN.sum()),
                  feeders_common_kWh=float(feeders.sum()), residual_common_kWh=float(residual.sum()),
                  mean_signed_slot_residual_kWh=float(residual.mean()), median_absolute_relative_residual=float(rel.median()),
                  residual_RMSE_kWh=float(np.sqrt(np.mean(residual**2))),
                  method="Compare MAIN once with six feeders on identical valid slots; independent public meter noise is not forced to close.")
    assert energy["median_absolute_relative_residual"] <= par["reconciliation_relative_median_limit"]
    return dict(status="PASS", production_max_mass_residual_t={k: float(v) for k, v in mass.items()},
                heat_to_shift_mass_residual_t=heat_errors, noisy_energy=energy)


@dataclass
class Analytics:
    tables: dict
    schema: dict
    availability: dict
    accounting: dict
    config: dict

    def write(self, directory):
        directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
        for name, frame in self.tables.items(): frame.to_parquet(directory / f"{name}.parquet", index=False)
        for name, content in (("feature_schema.yaml", self.schema), ("feature_availability.yaml", self.availability), ("config_snapshot.yaml", self.config)):
            (directory / name).write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
        (directory / "accounting_validation.json").write_text(json.dumps(self.accounting, indent=2, sort_keys=True)+"\n", encoding="utf-8")


def build_analytics(inputs=None, config=None):
    config = config or yaml.safe_load((ROOT / "configs/analytics_v1.yaml").read_text())
    validate_parameters(config); resolved = values(config)
    inputs = inputs or load_public_inputs(ROOT / "data/processed/sim_v1.1")
    clean = clean_readings(inputs, resolved["parameters"])
    production = production_register(inputs, resolved["parameters"])
    slots, slot_fields = slot_table(clean, production, inputs, resolved)
    heats, heat_fields = heat_table(inputs, slots, resolved)
    daily, daily_fields = asset_daily(clean, production, inputs, resolved)
    from .diagnostics import diagnostic_candidates
    alerts, alert_fields = diagnostic_candidates(heats, slots, resolved["parameters"])
    registry = Contracts(inputs.settings["timezone"])
    registry.add("heat_features", heats, ["heat_id"], heat_fields)
    registry.add("slot_features", slots, ["interval_start"], slot_fields)
    registry.add("asset_daily_metrics", daily, ["asset_id", "date"], daily_fields)
    registry.add("diagnostic_candidates", alerts, ["candidate_id"], alert_fields, access="diagnostic_only")
    pfields = {col: field("local datetime" if pd.api.types.is_datetime64_any_dtype(production[col]) else "t" if col.endswith("_t") else "percent" if col.endswith("pct") else "identifier or category", "available_at", "completed_shift_register", source="public production") for col in production}
    registry.add("production_register", production, ["plant_id", "date", "shift"], pfields)
    return Analytics(dict(heat_features=heats, slot_features=slots, asset_daily_metrics=daily,
                          diagnostic_candidates=alerts, production_register=production), registry.schema,
                     registry.availability(), accounting_checks(clean, inputs, resolved), config)
