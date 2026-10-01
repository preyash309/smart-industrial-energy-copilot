"""Explicit schema contract and allowlist loader; latent tables are internal."""
from __future__ import annotations
import numpy as np
import pandas as pd
import yaml
from energy_copilot.common import ROOT, parameter, validate_parameters

UNITS={
    "kW":"kW","kWh":"kWh","kVA":"kVA","kVAh":"kVAh","kWh_per_t":"kWh/t liquid", "pf":"dimensionless",
    "temp_C":"degC","tap_temp_C":"degC","ambient_C":"degC","flue_temp_C":"degC","fuel_kg":"kg coal",
    "vibration_mm_s":"mm/s","rpm":"rpm","pressure_bar":"bar","flow_m3_h":"m3/h",
    "rolling_yield_pct":"percent", "latent_wear":"dimensionless","latent_fouling":"dimensionless",
    "peak_kVA":"kVA"}
ALLOWED_OBS_FEATURES=["kW","kWh","kVA","kVAh","pf","fuel_kg","temp_C","vibration_mm_s","rpm","pressure_bar","flow_m3_h","flue_temp_C","state","tariff_band"]


def spec(name,kind,nullable=False,internal=False):
    unit=UNITS.get(name,"t" if name.endswith("_t") else "min" if name.endswith("_min") else "identifier or category" if kind=="string" else "local datetime" if kind=="datetime" else "dimensionless")
    role="internal_only" if internal else "target_or_audit_only" if name in {"fault_label","chem_ok","end","liquid_t","billet_t"} else "measurement" if name in ALLOWED_OBS_FEATURES else "join_or_register"
    lo=0 if kind=="number" and name not in {"temp_C","tap_temp_C","ambient_C","flue_temp_C"} else None
    hi=200 if name=="yard_stock_t" else 1 if name in {"latent_wear","latent_fouling"} else 100 if name=="rolling_yield_pct" else None
    # Observation glitches can put PF outside its engineering range; mark softly.
    if name=="pf" and internal:
        hi=1
    def limit(v):
        return parameter(v,unit,"derived","Phase-I schema and plant_v1.yaml","Null means no hard schema bound; physical validation has stricter state constraints.")
    return dict(type=kind,unit=unit,nullable=nullable,role=role,min=limit(lo),max=limit(hi))


def create_schema():
    readings={"timestamp":spec("timestamp","datetime"),"asset_id":spec("asset_id","string")}
    for name in ["kW","kWh","kVA","kVAh","pf","fuel_kg","temp_C","vibration_mm_s","rpm","pressure_bar","flow_m3_h","flue_temp_C"]:
        readings[name]=spec(name,"number",True)
    for name in ["state","tariff_band","measurement_status"]:
        readings[name]=spec(name,"string")
    readings["sensor_glitch"]=spec("sensor_glitch","boolean")
    heats={name:spec(name,"string" if name in {"heat_id","asset_id","fault_label"} else "datetime" if name in {"start","end"} else "boolean" if name=="chem_ok" else "number")
           for name in ["heat_id","asset_id","start","end","charge_t","liquid_t","billet_t","kWh","kWh_per_t","tap_temp_C","chem_ok","fault_label"]}
    production={name:spec(name,"string" if name in {"plant_id","date","shift"} else "number",name=="rolling_yield_pct")
                for name in ["plant_id","date","shift","billet_t","bar_t","rolled_billet_t","yard_stock_t","liquid_t","charge_t","melt_loss_t","cast_loss_t","rolling_loss_t","rolling_yield_pct"]}
    events={name:spec(name,"datetime" if name in {"start","end"} else "number" if name=="duration_min" else "string")
            for name in ["asset_id","start","end","type","label","duration_min"]}
    latent={k:spec(k,v["type"],v["nullable"],True) for k,v in readings.items() if k not in {"measurement_status","sensor_glitch"}}
    for name in ["working_day","latent_air_leak"]:
        latent[name]=spec(name,"boolean",internal=True)
    for name in ["latent_wear","latent_fouling","ambient_C","yard_stock_t","billet_t","liquid_t","charge_t","melt_loss_t","cast_loss_t","rolled_billet_t","bar_t","rolling_loss_t","if_powered_min","pump_available_min","mill_available_min","peak_kVA"]:
        latent[name]=spec(name,"number",internal=True)
    for name in ["fuel_input_GJ","fuel_base_GJ","fuel_fouling_GJ","fuel_holding_GJ"]:
        latent[name]=spec(name,"number",internal=True)
        latent[name]["unit"]="GJ"
        for bound in ["min","max"]:
            latent[name][bound]["unit"]="GJ"
    latent_heats={k:spec(k,v["type"],v["nullable"],True) for k,v in heats.items()}
    for name in ["day","start_min","end_min","powered_min","nonpowered_min","outage_min","best_kWh","practice_kWh","fault_kWh"]:
        latent_heats[name]=spec(name,"number",internal=True)
    schemas={name:dict(columns=columns,keys=keys,access=access) for name,columns,keys,access in [
        ("readings",readings,["timestamp","asset_id"],"downstream"),("heats",heats,["heat_id"],"targets_and_operator_register"),
        ("production",production,["plant_id","date","shift"],"operator_register"),("events",events,["asset_id","start","type","label"],"targets_only"),
        ("latent_truth",latent,["timestamp","asset_id"],"internal_only"),("latent_heats",latent_heats,["heat_id"],"internal_only") ]}
    result=dict(version="schema_v1.0",timestamp_convention="interval-start local plant time; timezone in config; end exclusive",
                readings_features=ALLOWED_OBS_FEATURES,forbidden_features=["latent_wear","latent_fouling","latent_air_leak","fault_label","future_failure_time","true_fault_severity","health","outage_min","fault_kWh"],
                notes="No automatic feature selection from numeric columns. Events/fault labels are targets only. Sensor-null fields may be not applicable or injected missingness.",tables=schemas)
    validate_parameters(result)
    (ROOT / "configs/schema.yaml").write_text(yaml.safe_dump(result,sort_keys=False),encoding="utf-8")
    return result


def validate_table(frame,table,schema=None):
    schema=schema or yaml.safe_load((ROOT / "configs/schema.yaml").read_text(encoding="utf-8"))
    contract=schema["tables"][table];cols=contract["columns"]
    if set(frame)!=set(cols):
        raise ValueError(f"{table} columns differ: {set(frame)^set(cols)}")
    if frame.duplicated(contract["keys"]).any():
        raise ValueError(f"Duplicate {table} key")
    for name,rules in cols.items():
        series=frame[name]
        if series.isna().any() and not rules["nullable"]:
            raise ValueError(f"Null {table}.{name}")
        present=series.dropna()
        if rules["type"]=="number":
            if not pd.api.types.is_numeric_dtype(series) or not np.isfinite(present).all():
                raise ValueError(f"Invalid numeric {table}.{name}")
            for bound,op in [("min",lambda x,y:x>=y-1e-8),("max",lambda x,y:x<=y+1e-8)]:
                value=rules[bound]["value"]
                if value is not None and not op(present,value).all():
                    raise ValueError(f"Range violation {table}.{name}")
        elif rules["type"]=="datetime" and not pd.api.types.is_datetime64_any_dtype(series):
            raise ValueError(f"Expected datetime {table}.{name}")
        elif rules["type"]=="boolean" and not pd.api.types.is_bool_dtype(series):
            raise ValueError(f"Expected boolean {table}.{name}")
        elif rules["type"]=="string" and not present.map(lambda x:isinstance(x,str)).all():
            raise ValueError(f"Expected string {table}.{name}")
    return True


def load_reading_features(directory):
    """The only downstream feature loader in Phase I; strictly observed allowlist."""
    frame=pd.read_parquet(Path(directory) / "readings.parquet")
    validate_table(frame,"readings")
    return frame[["timestamp","asset_id",*ALLOWED_OBS_FEATURES]].copy()


from pathlib import Path
