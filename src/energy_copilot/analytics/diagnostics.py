"""Observable evidence rules; candidates are neither fault labels nor savings."""
import json
import numpy as np
import pandas as pd
from .contracts import field


def diagnostic_candidates(heats, slots, parameters):
    rows = []
    def emit(at, asset, record, rule, metric, value, expected, unit, evidence, cause, n, confidence="low"):
        if not np.isfinite(value) or not np.isfinite(expected): return
        safe = {k: (float(v) if isinstance(v, (int, float, np.number)) and not isinstance(v, (bool, np.bool_)) else bool(v) if isinstance(v, (bool, np.bool_)) else str(v)) if pd.notna(v) else None for k, v in evidence.items()}
        rows.append(dict(candidate_id=f"C{len(rows):06d}", timestamp=at, available_at=at, asset_id=asset,
            source_id=record, rule=rule, metric=metric, measured_value=float(value), expected_value=float(expected),
            residual=float(value-expected), unit=unit, evidence_json=json.dumps(safe, sort_keys=True, allow_nan=False),
            possible_cause=cause, confidence=confidence, baseline_samples=int(n),
            limitation="Observable candidate only; noise, legitimate load/charge variation and an adaptive historical baseline can explain differences. Not a confirmed fault or avoidable-energy estimate."))
    for h in heats.itertuples():
        if h.expected_n < parameters["min_history"]: continue
        evidence = dict(tap_temp_C=h.tap_temp_C, duration_min=h.duration_min, SEC_kWh_per_t=h.SEC_kWh_per_t,
                        history_count=h.history_count, expected_method=h.expected_method, chem_ok=h.chem_ok)
        if h.residual_SEC > max(parameters["high_sec_min_residual"], parameters["residual_sd_multiplier"]*h.expected_SEC_sd):
            emit(h.available_at, "IF_01", h.heat_id, "high_heat_SEC", "SEC", h.actual_SEC, h.expected_SEC, "kWh/t liquid", evidence,
                 "Excess measured energy relative to past heats; inspect holding, charge preparation, lid practice and power trace.", h.expected_n)
        if h.duration_min-h.historical_duration_mean > max(parameters["long_heat_min_residual"], parameters["residual_sd_multiplier"]*h.historical_duration_sd):
            emit(h.available_at, "IF_01", h.heat_id, "long_heat", "duration", h.duration_min, h.historical_duration_mean, "min", evidence,
                 "Longer charging/melting/holding or cooling interruption; the heat log cannot distinguish these causes.", h.expected_n)
        if h.tap_temp_C > parameters["high_tap_temperature"] and h.residual_SEC > parameters["hot_heat_min_residual"]:
            emit(h.available_at, "IF_01", h.heat_id, "high_temperature_and_energy", "SEC", h.actual_SEC, h.expected_SEC, "kWh/t liquid", evidence,
                 "Excess thermal practice is a candidate because tap temperature and energy are both high; confirm the product temperature requirement.", h.expected_n, "moderate")
    idle = slots.MILL_01_state.eq("off") & slots.CMP_01_state.eq("running")
    for _, subset in slots.groupby("working_day", sort=True):
        load = subset.CMP_01_kW.where(idle.loc[subset.index])
        expectation = load.expanding().mean().shift(1); sd = load.expanding().std().shift(1)
        count = load.expanding().count().shift(1)
        for i in subset.index:
            if not idle.loc[i] or count.loc[i] < parameters["min_history"]: continue
            r = slots.loc[i]
            if r.CMP_01_kW-expectation.loc[i] > max(parameters["compressor_idle_min_residual"], parameters["residual_sd_multiplier"]*sd.loc[i]):
                emit(r.available_at, "CMP_01", str(r.interval_start), "compressor_mill_off_load", "power", r.CMP_01_kW, expectation.loc[i], "kW",
                     dict(mill_state=r.MILL_01_state, compressor_state=r.CMP_01_state, pressure_bar=r.CMP_01_pressure_bar, working_day=r.working_day),
                     "Compressor draw rose during observed mill-off periods; unloaded operation, air leakage or legitimate air demand are possibilities.", count.loc[i])
    time_key = slots.interval_start.dt.strftime("%H:%M")
    for _, subset in slots.groupby([time_key, slots.working_day], sort=True):
        x = subset.AUX_kW; expected = x.expanding().mean().shift(1); count = x.expanding().count().shift(1)
        for i in subset.index:
            r = slots.loc[i]
            if count.loc[i] >= parameters["min_history"] and abs(r.AUX_kW-expected.loc[i]) > parameters["auxiliary_relative_deviation"]*expected.loc[i]:
                emit(r.available_at, "AUX", str(r.interval_start), "auxiliary_load_deviation", "power", r.AUX_kW, expected.loc[i], "kW",
                     dict(hour=r.hour, weekday=r.weekday, auxiliary_state=r.AUX_state),
                     "Auxiliary demand differs from earlier same-clock periods; investigate ventilation, cranes, lighting or changed operations.", count.loc[i])
    for asset in ("MILL_01", "PMP_01"):
        power = slots[f"{asset}_kW"].where(slots[f"{asset}_state"].eq("running"))
        reference_count = parameters["machine_reference_samples"]
        for i, r in slots.iterrows():
            past = power.loc[:i].iloc[:-1].dropna()
            if len(past) < reference_count or not np.isfinite(power.loc[i]): continue
            expected = past.iloc[:reference_count].mean()
            if abs(power.loc[i]-expected) > parameters["machine_relative_deviation"]*expected:
                emit(r.available_at, asset, str(r.interval_start), "machine_power_deviation", "power", power.loc[i], expected, "kW",
                     dict(state=r[f"{asset}_state"], vibration_mm_s=r[f"{asset}_vibration_mm_s"],
                          temp_C=r[f"{asset}_temp_C"], flow_m3_h=r[f"{asset}_flow_m3_h"], rpm=r[f"{asset}_rpm"]),
                     "Power differs from the early observed running reference; load/throughput changes or mechanical condition may explain it.", reference_count)
    columns = ["candidate_id", "timestamp", "available_at", "asset_id", "source_id", "rule", "metric", "measured_value", "expected_value", "residual", "unit", "evidence_json", "possible_cause", "confidence", "baseline_samples", "limitation"]
    frame = pd.DataFrame(rows, columns=columns)
    frame = frame.sort_values(["timestamp", "asset_id", "rule", "candidate_id"], kind="stable").reset_index(drop=True)
    fields = {col: field("local datetime" if col in ("timestamp", "available_at") else "metric-specific; see unit" if col in ("measured_value", "expected_value", "residual") else "count" if col == "baseline_samples" else "identifier or text", "available_at", "diagnostic_evidence", source="observable public data plus strictly earlier historical baseline") for col in frame}
    return frame, fields
