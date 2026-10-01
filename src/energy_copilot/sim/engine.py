"""Common-clock process simulator with exact subslot furnace integration."""
from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from energy_copilot.common import ROOT, load_config, values, validate_parameters, canonical_hash, write_json
from energy_copilot.data.prepare import tariff_bands
from .scenario import ASSETS, CHANNELS, scenario, overlap, available_minutes, powered_segments


class InvariantError(ValueError):
    """Invalid physical operation must fail before data can be frozen."""


@dataclass
class Simulation:
    readings: pd.DataFrame
    heats: pd.DataFrame
    production: pd.DataFrame
    events: pd.DataFrame
    latent_truth: pd.DataFrame
    latent_heats: pd.DataFrame
    summary: dict
    scenario_manifest: dict
    config: dict

    def write(self, directory):
        target=Path(directory)
        target.mkdir(parents=True,exist_ok=True)
        for name in ("readings","heats","production","events","latent_truth","latent_heats"):
            getattr(self,name).to_parquet(target / f"{name}.parquet",index=False)
        write_json(target / "simulation_summary.json",self.summary)
        write_json(target / "scenario_manifest.json",self.scenario_manifest)
        (target / "config_snapshot.yaml").write_text(yaml.safe_dump(self.config,sort_keys=False),encoding="utf-8")


def simulate(config=None, schedule=None, practice=None, seed=42, days=30):
    """Return tables; .write(path) persists them. Schedule maps heat_id to local start.

    Practice accepts practice_loss and suppress_superheat/lid/half. No optimiser
    is included. Same seed + exogenous config replays the same scenario tape.
    Invalid schedules raise InvariantError, never silently clip production.
    """
    cfg=deepcopy(config) if isinstance(config,dict) else load_config(config)
    validate_parameters(cfg)
    c=values(cfg)
    if not isinstance(days,int) or days<=0:
        raise ValueError("days must be a positive integer")
    step=c["clock_minutes"]
    if step!=15:
        raise ValueError("Phase-I contract requires 15-minute clock")
    if seed is None:
        seed=c["seed"]
    start=pd.Timestamp(c["start"])
    if start.tz is not None or start != start.normalize():
        raise ValueError("Use timezone-naive local midnight plus declared config timezone")
    if c["material"]["initial_yard"]<0 or c["material"]["initial_yard"]>c["material"]["yard_max"]:
        raise InvariantError("Initial inventory outside bounds")
    if not all(0<c["material"][k]<=1 for k in ("cast_yield","rolling_yield")) or not 0<c["if"]["melt_yield"]<=1:
        raise InvariantError("Invalid material yields")
    for section in ("if","rhf","mill","pump","compressor","aux"):
        if not 0<c[section]["pf"]<=1:
            raise InvariantError("Invalid power factor")
    if not c["rhf"]["temp_min"]<=c["rhf"]["temp"]<=c["rhf"]["temp_max"]:
        raise InvariantError("RHF setpoint outside permitted bounds")
    # Draw the complete physical and measurement tape before reading decisions.
    tape=scenario(c,seed,days)
    n=days*1440//step
    times=pd.date_range(start,periods=n,freq=f"{step}min")
    daytimes=pd.date_range(start,periods=days,freq="D")
    working=np.array([t.dayofweek not in c["calendar"]["off_weekdays"] and t.strftime("%Y-%m-%d") not in c["calendar"]["maintenance_dates"] for t in daytimes])
    slotwork=np.repeat(working,1440//step)
    heatcount=c["calendar"]["heats_per_day"]
    f=c["faults"];m=c["material"];ifc=c["if"]
    pr=dict(practice or {})
    unknown=set(pr)-{"practice_loss","suppress_superheat","suppress_lid","suppress_half"}
    if unknown:
        raise ValueError(f"Unknown practice keys {unknown}")
    practice_loss=pr.get("practice_loss",ifc["practice_loss"])
    if practice_loss<0:
        raise ValueError("Practice loss must be nonnegative")
    sc=dict(schedule or {})
    used=set();heatrows=[];segments=[];events=deepcopy(tape["events"])
    casts=np.zeros(n);liquid=np.zeros(n);charge=np.zeros(n);castloss=np.zeros(n);meltloss=np.zeros(n)
    for day in range(days):
        if not working[day]:
            continue
        cursor=float(day*1440)
        for ordinal in range(heatcount):
            index=day*heatcount+ordinal
            heat_id=f"D{day:03d}_H{ordinal:02d}"
            heatstart=cursor
            if heat_id in sc:
                requested=sc[heat_id]
                heatstart=float((pd.Timestamp(requested)-start)/pd.Timedelta(minutes=1)) if isinstance(requested,(str,pd.Timestamp)) else float(requested)
                if abs(heatstart-cursor)<=c["acceptance"]["tolerance"]:
                    heatstart=cursor  # Timestamp nanosecond round-trip cannot introduce a spurious overlap.
                if heatstart<cursor-1e-8 or heatstart<day*1440 or heatstart>=(day+1)*1440:
                    raise InvariantError("Schedule has overlapping heat or wrong working day")
                used.add(heat_id)
            flags={key:bool(tape[key][index]) for key in ("superheat","lid","half","charge_bad")}
            for key in ("superheat","lid","half"):
                if pr.get(f"suppress_{key}",False):
                    flags[key]=False
            losses={"superheat":f["superheat_loss"] if flags["superheat"] else 0.,
                    "lid":f["lid_loss"] if flags["lid"] else 0.,
                    "charge_bad":float(tape["charge_loss"][index]) if flags["charge_bad"] else 0.,
                    "half":f["half_loss"] if flags["half"] else 0.}
            # V0 baseline is a deterministic effective 650-kWh/t heat, no random labels.
            fault_loss=sum(losses.values()) if c["stochastic"] else ifc["baseline_fault_loss"]
            chronic=max(0.,practice_loss+float(tape["practice_delta"][index]))
            sec=ifc["best_sec"]+chronic+fault_loss
            tonnes=ifc["liquid_per_heat"]
            energy=sec*tonnes
            powerstart=heatstart+ifc["nonpowered_min"]+float(tape["delay"][index])
            half_energy=min(energy,ifc["rated_kw"]*f["half_fraction"]*f["half_minutes"]/60) if flags["half"] else 0.
            powersegments=[]
            t=powerstart
            if half_energy:
                part,t=powered_segments(t,half_energy,ifc["rated_kw"]*f["half_fraction"],tape["repairs"]["PMP_01"])
                powersegments.extend(part)
            part,end=powered_segments(t,energy-half_energy,ifc["rated_kw"],tape["repairs"]["PMP_01"])
            powersegments.extend(part)
            if end>(day+1)*1440+1e-8:
                raise InvariantError(f"{heat_id} cannot complete daily target within working day: end {end-day*1440:.2f} min")
            powered_min=sum(b-a for a,b,power in powersegments)
            temp=ifc["tap_temp"]+(f["superheat_k"] if flags["superheat"] else 0.)
            if not ifc["tap_min"]<=temp<=ifc["tap_max"]:
                raise InvariantError("Tap temperature outside declared quality window")
            fault_labels="|".join(key for key,v in flags.items() if v)
            row=dict(heat_id=heat_id,asset_id="IF_01",day=day,start=start+pd.Timedelta(minutes=heatstart),
                     end=start+pd.Timedelta(minutes=end),start_min=heatstart,end_min=end,
                     charge_t=tonnes/ifc["melt_yield"],liquid_t=tonnes,billet_t=tonnes*m["cast_yield"],
                     kWh=energy,kWh_per_t=sec,tap_temp_C=temp,chem_ok=True, fault_label=fault_labels,
                     powered_min=powered_min,nonpowered_min=ifc["nonpowered_min"]+float(tape["delay"][index]),
                     outage_min=end-powerstart-powered_min,best_kWh=tonnes*ifc["best_sec"],
                     practice_kWh=tonnes*chronic,fault_kWh=tonnes*fault_loss)
            heatrows.append(row)
            segments.extend((a,b,power,heat_id) for a,b,power in powersegments)
            for label,active in flags.items():
                if active:
                    event_end=end
                    if label=="lid":
                        event_end=min(end,powerstart+f["lid_minutes"])
                    if label=="half":
                        event_end=min(end,powerstart+f["half_minutes"])
                    events.append(dict(asset_id="IF_01",start_min=powerstart,end_min=event_end,type="fault",label=label))
            tap_slot=min(n-1,int(np.ceil(end/step)-1))
            liquid[tap_slot]+=tonnes;casts[tap_slot]+=row["billet_t"]
            charge[tap_slot]+=row["charge_t"];meltloss[tap_slot]+=row["charge_t"]-tonnes;castloss[tap_slot]+=tonnes-row["billet_t"]
            cursor=end
    if set(sc)!=used:
        raise InvariantError(f"Unknown/nonworking heat IDs in schedule: {set(sc)-used}")
    htrue=pd.DataFrame(heatrows)
    if htrue.empty:
        htrue=pd.DataFrame(columns=["heat_id","asset_id","day","start","end","start_min","end_min","charge_t","liquid_t","billet_t","kWh","kWh_per_t","tap_temp_C","chem_ok","fault_label","powered_min","nonpowered_min","outage_min","best_kWh","practice_kWh","fault_kWh"])
    if_energy=np.zeros(n);if_powered=np.zeros(n);if_peak=np.zeros(n)
    for a,b,power,heat_id in segments:
        for i in range(max(0,int(a//step)),min(n,int(np.ceil(b/step)))):
            mins=overlap(i*step,(i+1)*step,a,b)
            if_energy[i]+=power*mins/60;if_powered[i]+=mins;if_peak[i]=max(if_peak[i],power)
    calibration=values(yaml.safe_load((ROOT / c["calibration_file"]).read_text(encoding="utf-8")))
    blend=c["aux"]["profile_blend"]
    weekday=np.array(calibration["weekday_profile"]);weekend=np.array(calibration["weekend_profile"])
    profile=np.array([weekend[i%96] if ts.dayofweek>=5 else weekday[i%96] for i,ts in enumerate(times)])
    aux_kw=c["aux"]["average_kw"]*(1-blend+blend*profile)*np.where(slotwork,1,c["aux"]["offday_fraction"])
    roll=np.zeros(n);bars=np.zeros(n);stock=np.zeros(n);coal=np.zeros(n);rhf_kw=np.zeros(n);mill_kw=np.zeros(n)
    fuel_base=np.zeros(n);fuel_fouling=np.zeros(n);fuel_holding=np.zeros(n)
    pump_kw=np.zeros(n);pump_flow=np.zeros(n);pump_avail=np.zeros(n);mill_avail=np.zeros(n);cmp_kw=np.zeros(n)
    yard=m["initial_yard"];dayrolled=0.
    for i,ts in enumerate(times):
        a,b=i*step,(i+1)*step
        if i%96==0:
            dayrolled=0.
        pw=tape["wear"]["PMP_01"][i];mw=tape["wear"]["MILL_01"][i]
        pa=available_minutes(a,b,tape["repairs"]["PMP_01"])
        ma=available_minutes(a,b,tape["repairs"]["MILL_01"])
        pump_avail[i]=pa;mill_avail[i]=ma
        running=bool(slotwork[i])
        pump_base=c["pump"]["rating_kw"]
        if c["stochastic"]:
            pump_base*= (1-f["pump_efficiency_loss"])/(1-f["pump_efficiency_loss"]*pw)
        pump_kw[i]=pump_base*pa/step if running else 0.
        pump_flow[i]=c["pump"]["flow"]*(1-f["pump_flow_loss"]*pw) if running and pa>0 else 0.
        if if_powered[i]>pa+1e-8 or (if_powered[i]>0 and pump_flow[i]<c["pump"]["min_flow"]):
            raise InvariantError("Cooling permissive/interlock violated")
        hour=ts.hour+ts.minute/60
        mill_window=running and c["calendar"]["mill_start_hour"]<=hour<c["calendar"]["mill_start_hour"]+c["calendar"]["mill_hours"]
        if mill_window:
            # Consume opening inventory only. Same-slot tap enters the yard afterwards.
            feed=min(yard,min(c["mill"]["capacity_tph"],c["rhf"]["capacity_tph"])*ma/60,max(0,m["billet_target"]-dayrolled))
            roll[i]=feed;bars[i]=feed*m["rolling_yield"];dayrolled+=feed;yard-=feed
            mill_kw[i]=bars[i]*c["mill"]["sec"]*(1+f["mill_energy_gain"]*mw)/ (step/60)
            rhf_kw[i]=c["rhf"]["electric_kw"]
            fuel_base[i]=bars[i]*c["rhf"]["fuel_sec"]
            fuel_fouling[i]=fuel_base[i]*f["fouling_loss"]*tape["fouling"][i]
            fuel_holding[i]=c["rhf"]["hold_fuel"]*(step-ma)/60*c["rhf"]["coal_ncv"]/1000
            coal[i]=(fuel_base[i]+fuel_fouling[i]+fuel_holding[i])/c["rhf"]["coal_ncv"]*1000
        yard+=casts[i];stock[i]=yard
        if not m["yard_min"]-1e-8<=yard<=m["yard_max"]+1e-8:
            raise InvariantError(f"Yard bound failed at {ts}: {yard}")
        cmp_kw[i]=(c["compressor"]["loaded_kw"] if mill_window else c["compressor"]["idle_kw"]) if running else c["compressor"]["idle_kw"]*c["aux"]["offday_fraction"]
        if tape["leak"][i]:
            cmp_kw[i]=min(c["compressor"]["rating_kw"],cmp_kw[i]+f["leak_extra_kw"])
    kw=np.column_stack([if_energy/(step/60),rhf_kw,mill_kw,pump_kw,cmp_kw,aux_kw])
    pfs=np.array([c[k]["pf"] for k in ("if","rhf","mill","pump","compressor","aux")])
    kvar=kw*np.tan(np.arccos(pfs))
    main_kw=kw.sum(axis=1);main_q=kvar.sum(axis=1);main_kva=np.hypot(main_kw,main_q)
    main_pf=np.divide(main_kw,main_kva,out=np.ones(n),where=main_kva>0)
    # Peak IF subslot concurrency is checked, not merely diluted slot-average kVA.
    other_peak=kw[:,1:].copy();other_peak[:,2]=np.where(slotwork,c["pump"]["rating_kw"],0)
    # Mill kW during available fraction; repair averaging cannot hide drive peaks.
    other_peak[:,1]=np.divide(mill_kw,mill_avail/step,out=np.zeros(n),where=mill_avail>0)
    peaks=np.column_stack([if_peak,other_peak])
    peak_kva=np.hypot(peaks.sum(axis=1),(peaks*np.tan(np.arccos(pfs))).sum(axis=1))
    if peak_kva.max()>c["acceptance"]["contract_kva"]+1e-8:
        raise InvariantError(f"Peak concurrency exceeds contract: {peak_kva.max():.1f} kVA")
    if mill_kw.max()>c["mill"]["rating_kw"]+1e-8:
        raise InvariantError("Mill drive exceeds rating")
    allkw=np.column_stack([kw,main_kw]);allkva=np.column_stack([kw/pfs,main_kva]);allpf=np.column_stack([np.tile(pfs,(n,1)),main_pf])
    bands=tariff_bands(times,c["tariff"])
    truthrows=[]
    for i,ts in enumerate(times):
        mw=tape["wear"]["MILL_01"][i];pw=tape["wear"]["PMP_01"][i]
        for j,asset in enumerate(ASSETS):
            active=allkw[i,j]>0
            wear=mw if asset=="MILL_01" else pw if asset=="PMP_01" else 0.
            temp=np.nan;vibration=np.nan;rpm=np.nan;flow=np.nan;pressure=np.nan
            if asset=="IF_01":
                temp=ifc["tap_temp"] if if_powered[i]>0 else tape["ambient"][i]
            elif asset=="RHF_01":
                temp=c["rhf"]["temp"] if rhf_kw[i]>0 else tape["ambient"][i]
            elif asset=="MILL_01":
                temp=c["mill"]["base_temp"]+f["mill_temp_gain"]*mw+tape["ambient"][i]-c["weather"]["mean"]
                vibration=c["mill"]["base_vibration"]+f["mill_vibration_gain"]*mw;rpm=c["mill"]["rpm"] if mill_kw[i]>0 else 0.
            elif asset=="PMP_01":
                temp=c["pump"]["base_temp"]+f["pump_temp_gain"]*pw+tape["ambient"][i]-c["weather"]["mean"]
                vibration=c["pump"]["base_vibration"]+f["pump_vibration_gain"]*pw;flow=pump_flow[i]
            elif asset=="CMP_01":
                pressure=c["compressor"]["pressure"]
            state="running" if active else "off"
            if asset in tape["repairs"] and available_minutes(i*step,(i+1)*step,tape["repairs"][asset])<step:
                state="repair_partial" if active else "repair"
            truthrows.append(dict(timestamp=ts,asset_id=asset,kW=allkw[i,j],kWh=allkw[i,j]*step/60,
                       kVA=allkva[i,j],kVAh=allkva[i,j]*step/60,pf=allpf[i,j],
                       fuel_kg=coal[i] if asset=="RHF_01" else 0.,temp_C=temp,vibration_mm_s=vibration,
                       fuel_input_GJ=coal[i]*c["rhf"]["coal_ncv"]/1000 if asset=="RHF_01" else 0.,
                       fuel_base_GJ=fuel_base[i] if asset=="RHF_01" else 0.,fuel_fouling_GJ=fuel_fouling[i] if asset=="RHF_01" else 0.,
                       fuel_holding_GJ=fuel_holding[i] if asset=="RHF_01" else 0.,
                       rpm=rpm,pressure_bar=pressure,flow_m3_h=flow,state=state,tariff_band=bands[i],
                       working_day=bool(slotwork[i]),latent_wear=wear,latent_fouling=tape["fouling"][i] if asset=="RHF_01" else 0.,
                       latent_air_leak=bool(tape["leak"][i]) if asset=="CMP_01" else False,
                       ambient_C=tape["ambient"][i],flue_temp_C=c["rhf"]["flue_temp"]+f["fouling_flue"]*tape["fouling"][i] if asset=="RHF_01" else np.nan,
                       yard_stock_t=stock[i],billet_t=casts[i],liquid_t=liquid[i],charge_t=charge[i],melt_loss_t=meltloss[i],
                       cast_loss_t=castloss[i],rolled_billet_t=roll[i],bar_t=bars[i],rolling_loss_t=roll[i]-bars[i],
                       if_powered_min=if_powered[i],pump_available_min=pump_avail[i],mill_available_min=mill_avail[i],peak_kVA=peak_kva[i]))
    truth=pd.DataFrame(truthrows)
    observed=truth[["timestamp","asset_id",*CHANNELS,"flue_temp_C","state","tariff_band"]].copy()
    obs=c["observations"]
    missing_flags=np.zeros(n*len(ASSETS),dtype=bool)
    glitch_flags=np.zeros(n*len(ASSETS),dtype=bool)
    rhf_rows=observed.asset_id.eq("RHF_01").to_numpy()
    for k,col in enumerate(CHANNELS):
        original=observed[col].to_numpy(dtype=float)
        sd=obs["relative_noise"] if col in {"kW","kWh","kVA","kVAh","pf","fuel_kg"} else obs["sensor_noise"]
        noise=tape["noise"][:,:,k].ravel().copy()
        if col=="temp_C":
            noise[rhf_rows]=tape["rhf_zone_noise"]
        measured=original*(1+sd*noise)
        if col=="pf":
            measured=np.clip(measured,0,1)
        elif col!="temp_C":
            measured=np.maximum(0,measured)
        if c["stochastic"]:
            glitches=tape["glitch_draw"][:,:,k].ravel()<obs["glitch_probability"]
            missing=tape["missing_draw"][:,:,k].ravel()<obs["missing_probability"]
            glitch_flags|=glitches&np.isfinite(original)&~missing
            missing_flags|=missing&np.isfinite(original)
            measured=np.where(glitches,measured*obs["glitch_multiplier"],measured)
            measured=np.where(missing,np.nan,measured)
        observed[col]=measured
    # Independent zone/flue measurement processes prevent shared-noise cancellation.
    # The configured scale is unchanged; truth/fuel/production never see these draws.
    observed.loc[rhf_rows,"flue_temp_C"]*=1+obs["sensor_noise"]*tape["rhf_flue_noise"]
    observed["measurement_status"]=np.where(missing_flags,"partial_missing",np.where(glitch_flags,"glitch","observed"))
    observed["sensor_glitch"]=glitch_flags
    public_heats=htrue[["heat_id","asset_id","start","end","charge_t","liquid_t","billet_t","kWh","kWh_per_t","tap_temp_C","chem_ok","fault_label"]].copy()
    if len(public_heats):
        ix=np.minimum(n-1, np.floor(htrue.end_min.to_numpy(dtype=float)/step).astype(int))
        public_heats["kWh"]*=1+obs["relative_noise"]*tape["noise"][ix,0,0]
        public_heats["kWh_per_t"]=public_heats.kWh/public_heats.liquid_t
        public_heats["tap_temp_C"]*=1+obs["sensor_noise"]*tape["noise"][ix,0,6]
    main=truth[truth.asset_id.eq("MAIN")].copy()
    main["date"]=main.timestamp.dt.strftime("%Y-%m-%d");main["shift"]=(main.timestamp.dt.hour//8).astype(str)
    prod=main.groupby(["date","shift"],sort=True).agg(billet_t=("billet_t","sum"),bar_t=("bar_t","sum"),
               rolled_billet_t=("rolled_billet_t","sum"),yard_stock_t=("yard_stock_t","last"),liquid_t=("liquid_t","sum"),
               charge_t=("charge_t","sum"),melt_loss_t=("melt_loss_t","sum"),cast_loss_t=("cast_loss_t","sum"),rolling_loss_t=("rolling_loss_t","sum")).reset_index()
    prod.insert(0,"plant_id",c["plant_id"])
    prod["rolling_yield_pct"]=np.where(prod.rolled_billet_t>0,100*prod.bar_t/prod.rolled_billet_t,np.nan)
    if c["stochastic"]:
        if tape["leak"].any():
            events.append(dict(asset_id="CMP_01",start_min=f["leak_onset_day"]*1440,end_min=days*1440,type="fault",label="air_leak"))
        if tape["fouling"].max()>0:
            events.append(dict(asset_id="RHF_01",start_min=0.,end_min=days*1440,type="fault",label="recuperator_fouling"))
    erows=[dict(asset_id=e["asset_id"],start=start+pd.Timedelta(minutes=e["start_min"]),end=start+pd.Timedelta(minutes=min(e["end_min"],days*1440)),
                type=e["type"],label=e["label"],duration_min=min(e["end_min"],days*1440)-e["start_min"]) for e in events]
    eventframe=pd.DataFrame(erows,columns=["asset_id","start","end","type","label","duration_min"])
    if len(eventframe):
        eventframe=eventframe.sort_values(["start","asset_id","type","label"],kind="stable").reset_index(drop=True)
    scenario_manifest=dict(seed=int(seed),days=days,start=str(start),timezone=c["timezone"],scenario_sha256=tape["hash"],
              config_sha256=canonical_hash(cfg),decisions_sha256=canonical_hash(dict(schedule=sc,practice=pr)),
              exogenous_order="charge/practice marks, delays, calendar wear-to-threshold repairs, weather, sensor tapes BEFORE decisions",
              replay_boundary="Keep horizon, calendar, heat identity/count and physical exogenous settings fixed; decisions may change starts/practice only.",
              rng="numpy.random.Generator / SeedSequence stable SHA256 named streams",
              observation_model="v1.1: independent named RHF zone/flue temperature streams; unchanged configured sensor_noise")
    result=Simulation(observed,public_heats,prod,eventframe,truth,htrue,{},scenario_manifest,cfg)
    from .validate import validate_simulation
    result.summary=validate_simulation(result,baseline=(not sc and not pr))
    return result
