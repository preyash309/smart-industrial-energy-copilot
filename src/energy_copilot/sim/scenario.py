"""Exogenous tape is generated before any operating decision is inspected."""
from __future__ import annotations
import numpy as np
import pandas as pd
from energy_copilot.common import rng_streams, canonical_hash

ASSETS = ("IF_01", "RHF_01", "MILL_01", "PMP_01", "CMP_01", "AUX", "MAIN")
CHANNELS = ("kW","kWh","kVA","kVAh","pf","fuel_kg","temp_C","vibration_mm_s","rpm","pressure_bar","flow_m3_h")
RHF_ZONE_STREAM = "rhf_zone_temperature"
RHF_FLUE_STREAM = "rhf_flue_temperature"


def scenario(config, seed, days):
    c=config; f=c["faults"]
    step=c["clock_minutes"]
    total=days*1440
    n=total//step
    # Heat marks use stable day/ordinal identifiers, never decision-dependent draw order.
    count=days*c["calendar"]["heats_per_day"]
    streams=rng_streams(seed,["charge","practice","delays","if_faults","wear_mill","wear_pump","weather","observation",
                             RHF_ZONE_STREAM,RHF_FLUE_STREAM])
    def marks(prob):
        return streams["if_faults"].random(count)<prob if c["stochastic"] else np.zeros(count,dtype=bool)
    tape={"superheat":marks(f["superheat_probability"]),"lid":marks(f["lid_probability"]),
          "half":marks(f["half_probability"])}
    tape["charge_bad"]=streams["charge"].random(count)<f["charge_probability"] if c["stochastic"] else np.zeros(count,dtype=bool)
    tape["charge_loss"]=streams["charge"].uniform(*f["charge_loss"],count)
    tape["practice_delta"]=streams["practice"].normal(0,f["practice_sd"],count) if c["stochastic"] else np.zeros(count)
    tape["delay"]=np.where(streams["delays"].random(count)<f["delay_probability"],streams["delays"].uniform(0,f["delay_max"],count),0) if c["stochastic"] else np.zeros(count)
    t=(np.arange(n)+.5)*step
    tape["ambient"]=c["weather"]["mean"]+c["weather"]["daily_amplitude"]*np.sin(2*np.pi*(t%1440)/1440)
    if c["stochastic"]:
        tape["ambient"]+=streams["weather"].normal(0,c["weather"]["sd"],n)
    tape["wear"]={}
    tape["repairs"]={}
    events=[]
    for asset,stream in [("MILL_01","wear_mill"),("PMP_01","wear_pump")]:
        intervals=[]; age_start=0.; initial=f["initial_wear"]; wear=np.zeros(n)
        while age_start<total and c["stochastic"]:
            life=streams[stream].uniform(*f["wear_days"])*1440
            failure=age_start+(1-initial)*life
            repair=streams[stream].uniform(*f["repair_hours"])*60
            sel=(t>=age_start)&(t<min(failure,total))
            wear[sel]=initial+(t[sel]-age_start)/life
            if failure>=total:
                break
            intervals.append((failure,failure+repair))
            label="bearing_wear" if asset=="MILL_01" else "impeller_wear"
            events.extend([dict(asset_id=asset,start_min=failure,end_min=failure+repair,type="failure",label=label),
                           dict(asset_id=asset,start_min=failure,end_min=failure+repair,type="repair",label=f"{label}_replacement")])
            age_start=failure+repair;initial=0.
        tape["wear"][asset]=wear
        tape["repairs"][asset]=intervals
    tape["leak"]=((t/1440)>=f["leak_onset_day"]) & c["stochastic"] & (f["leak_extra_kw"]>0)
    tape["fouling"]=np.minimum(t/1440*f["fouling_daily"],1) if c["stochastic"] else np.zeros(n)
    shape=(n,len(ASSETS),len(CHANNELS))
    obs=streams["observation"]
    tape["noise"]=obs.normal(0,1,shape) if c["stochastic"] else np.zeros(shape)
    tape["missing_draw"]=obs.random(shape)
    tape["glitch_draw"]=obs.random(shape)
    # Dedicated named streams preserve every existing physical/other-sensor draw.
    # Generate both observation tapes before decisions; never use them in physics.
    tape["rhf_zone_noise"]=streams[RHF_ZONE_STREAM].normal(0,1,n) if c["stochastic"] else np.zeros(n)
    tape["rhf_flue_noise"]=streams[RHF_FLUE_STREAM].normal(0,1,n) if c["stochastic"] else np.zeros(n)
    tape["events"]=events
    # No wall-clock time, paths, schedule, practice or observation-rate setting in tape identity.
    identity={k:({a:v.tolist() for a,v in value.items()} if k=="wear" else value.tolist() if isinstance(value,np.ndarray) else value)
              for k,value in tape.items()}
    tape["hash"]=canonical_hash(identity)
    return tape


def overlap(a,b,x,y):
    return max(0.,min(b,y)-max(a,x))


def available_minutes(a,b,repairs):
    return b-a-sum(overlap(a,b,x,y) for x,y in repairs)


def powered_segments(start,energy,power,repairs,flow=None):
    """Consume exact electrical energy; pauses for exogenous pump outages."""
    left=energy; cursor=start; segments=[]
    for x,y in repairs:
        if y<=cursor:
            continue
        available=max(0.,x-cursor)
        take=min(left,power*available/60)
        if take>0:
            end=cursor+take/power*60;segments.append((cursor,end,power));left-=take;cursor=end
        if left<=1e-10:
            return segments,cursor
        cursor=max(cursor,y)
    end=cursor+left/power*60
    segments.append((cursor,end,power))
    return segments,end
