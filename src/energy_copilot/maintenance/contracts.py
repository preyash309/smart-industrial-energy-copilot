"""Strict public maintenance controls and immutable completed-service records."""
from dataclasses import dataclass
from datetime import datetime
import math
import pandas as pd
from energy_copilot.common import load_config,values


def settings(path='configs/maintenance_v1.yaml'):
    return values(load_config(path))


@dataclass(frozen=True)
class MaintenanceAction:
    asset_id: str
    start_time: str
    duration_min: int
    intervention_type: str = 'preventive_replacement'
    condition_effect: str = 'reset_wear'
    direct_cost: float | None = None

    @property
    def end_time(self):
        return (pd.Timestamp(self.start_time)+pd.Timedelta(minutes=self.duration_min)).isoformat()

    def validate(self, config, plant_start, days):
        c=values(config);types=c['service']
        if self.asset_id not in types:raise ValueError('Unsupported maintenance asset')
        rule=types[self.asset_id];at=pd.Timestamp(self.start_time);base=pd.Timestamp(plant_start)
        if at.tz is not None or at!=at.floor('15min') or not base<=at<base+pd.Timedelta(days=days):raise ValueError('Invalid maintenance start/clock')
        if at.minute or at.hour not in rule['candidate_start_hour']:raise ValueError('Unsupported preventive-service window')
        if not isinstance(self.duration_min,int) or self.duration_min!=rule['duration_min'] or self.duration_min<=0 or self.duration_min%15:raise ValueError('Unsupported maintenance duration')
        if at+pd.Timedelta(minutes=self.duration_min+rule['restart_delay_min'])>base+pd.Timedelta(days=days):raise ValueError('Maintenance outside physical horizon')
        if self.intervention_type!=rule['intervention_type'] or self.condition_effect!=rule['condition_effect']:raise ValueError('Unknown intervention/effect')
        if (self.direct_cost is None)!=(rule['direct_cost_Rs'] is None):raise ValueError('Maintenance cost contract mismatch')
        if self.direct_cost is not None and (not math.isfinite(self.direct_cost) or self.direct_cost!=rule['direct_cost_Rs']):raise ValueError('Invalid maintenance direct cost')
        return self


def validate_actions(actions,config,plant_start,days):
    rows=tuple(x if isinstance(x,MaintenanceAction) else MaintenanceAction(**x) for x in actions)
    for row in rows:row.validate(config,plant_start,days)
    for asset in ('MILL_01','PMP_01'):
        selected=sorted((r for r in rows if r.asset_id==asset),key=lambda r:r.start_time)
        for a,b in zip(selected,selected[1:]):
            if pd.Timestamp(a.end_time)>pd.Timestamp(b.start_time):raise ValueError('Overlapping preventive services')
    return tuple(sorted(rows,key=lambda r:(r.start_time,r.asset_id)))


@dataclass(frozen=True)
class ExecutedMaintenance:
    asset_id: str
    start_time: str
    end_time: str
    intervention_type: str
    condition_effect: str

    def validate(self,now,config,plant_start,days):
        duration=int((pd.Timestamp(self.end_time)-pd.Timestamp(self.start_time)).total_seconds()/60)
        MaintenanceAction(self.asset_id,self.start_time,duration,self.intervention_type,self.condition_effect).validate(config,plant_start,days)
        if pd.Timestamp(self.end_time)>pd.Timestamp(now):raise ValueError('Uncompleted service cannot be frozen')
        return self
