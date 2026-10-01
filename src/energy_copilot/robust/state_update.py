"""Only posted public observations and immutable execution acknowledgements enter state."""
from dataclasses import asdict, replace
from datetime import timedelta
import math
import pandas as pd
from energy_copilot.forecast import PredictionService
from energy_copilot.optimization.contracts import HeatCandidate,ProductionOrder
from energy_copilot.replay.history import posted_history
from energy_copilot.schema import ALLOWED_OBS_FEATURES
from .contracts import ReplanState,RemainingInput,ExecutedHeatDecision


def public_snapshot(sim,current_time):
    """Project BEFORE handing anything to the controller. No event/truth access."""
    at=pd.Timestamp(current_time)
    columns=['timestamp','asset_id',*ALLOWED_OBS_FEATURES,'sensor_glitch','measurement_status']
    readings=sim.readings.loc[sim.readings.timestamp+pd.Timedelta(minutes=15)<=at,columns].copy()
    heats=sim.heats.loc[sim.heats.end<=at,['heat_id','asset_id','start','end','charge_t','liquid_t','billet_t','kWh','kWh_per_t','tap_temp_C','chem_ok']].copy()
    production=sim.production.copy()
    posted=pd.to_datetime(production.date)+pd.to_timedelta((production['shift'].astype(int)+1)*8,unit='h')
    production=production.loc[posted<=at].copy()
    return readings,heats,production


def update_state(previous, current_time, public_heats, executed_rolling, executed_decisions,template):
    at=pd.Timestamp(current_time);origin=pd.Timestamp(template.forecast_origin)
    frozen=tuple(x if isinstance(x,ExecutedHeatDecision) else ExecutedHeatDecision(**x) for x in executed_decisions)
    if previous is not None:
        if at<=pd.Timestamp(previous.current_time):raise ValueError('Clock must advance')
        if frozen[:len(previous.frozen_executed_decisions)]!=previous.frozen_executed_decisions:raise ValueError('Executed heat changed')
        if tuple(executed_rolling[:len(previous.executed_rolling)])!=previous.executed_rolling:raise ValueError('Executed rolling changed')
    h=public_heats.loc[(public_heats.start>=origin)&(public_heats.end<=at)].sort_values('start')
    completed=tuple(h.heat_id);remaining=tuple(x.heat_id for x in template.heats if x.heat_id not in completed)
    # Material register reconstruction: posted heat billet weights + accepted feed
    # acknowledgements. No yard_stock_t from hidden physical truth is read.
    stock=template.initial_inventory_t+float(h.billet_t.sum())-sum(executed_rolling)
    state=ReplanState(at.isoformat(),completed,remaining,stock,tuple(executed_rolling),frozen,template.equipment_availability)
    return state.validate(template)


def remaining_input(template,state,public_tables,plant,service,mode='central',grid=5,not_before=None):
    if not isinstance(service,PredictionService):raise TypeError('Public PredictionService required')
    state.validate(template);at=pd.Timestamp(state.current_time);base=pd.Timestamp(template.forecast_origin);geometry=at.floor('15min')
    offset=int((geometry-base).total_seconds()/900);n=96-offset
    if n<=0 or not state.remaining_heats:raise ValueError('No remaining scheduling horizon')
    heat,_,health,_,provenance=posted_history(*public_tables,plant,geometry.isoformat())
    completed=public_tables[1].sort_values('end')
    duration=(completed.end-completed.start).dt.total_seconds()/60;sec=completed.kWh/completed.liquid_t
    def numeric(v):return None if pd.isna(v) else float(v)
    heat['features'].update(previous_heat_SEC=numeric(sec.iloc[-1]),previous_heat_duration=numeric(duration.iloc[-1]),rolling_mean_SEC=numeric(sec.tail(20).mean()),global_mean_SEC=numeric(sec.mean()),historical_duration_mean=numeric(duration.mean()))
    for name in ('previous_heat_SEC','previous_heat_duration','rolling_mean_SEC','global_mean_SEC','historical_duration_mean'):heat['available_at'][name]=state.current_time
    health=tuple(dict(ctx,forecast_origin=state.current_time) for ctx in health)
    candidates=[];orders=tuple(h for h in template.heats if h.heat_id in state.remaining_heats)
    for h in orders:
        cache={}
        for minute in range(0,n*15,grid):
            start=geometry+pd.Timedelta(minutes=minute);practice='practice_loss_40';key=start.hour
            if start<at:continue
            if not_before is not None and start<pd.Timestamp(not_before):continue
            if key not in cache:
                f=dict(heat['features'],hour=start.hour,weekday=start.weekday(),shift=start.hour//8,
                       practice_loss_kWh_t=service.contract['practice_modes'][practice]['practice_loss_kWh_t'],candidate_liquid_t=h.liquid_t)
                posting=dict(heat['available_at'],**{k:state.current_time for k in ('hour','weekday','shift','practice_loss_kWh_t','candidate_liquid_t')})
                cache[key]=service.predict_heat(dict(heat_id=h.heat_id,forecast_origin=state.current_time,candidate_start=start.isoformat(),features=f,available_at=posting),practice)
            candidates.append(HeatCandidate(f'{h.heat_id}:{state.current_time}:{minute}:{practice}',h.heat_id,start.isoformat(),cache[key]))
    hp=tuple(service.predict_health(x,24) for x in health)
    partial=at!=geometry;first_feed=state.executed_rolling[-1] if partial else None
    current_cast=float(completed.loc[(completed.end>geometry)&(completed.end<=at),'billet_t'].sum()) if partial else 0.0
    known=tuple([0.0,current_cast]+[0.0]*(n-1))
    prior_feed=sum(state.executed_rolling)-(first_feed or 0.0)
    opening=state.actual_inventory_t+(first_feed or 0.0)-current_cast
    order=ProductionOrder(max(0,template.production_order.bars_t-prior_feed*template.constraints.rolling_yield),
                          sum(h.liquid_t*template.constraints.cast_yield for h in orders)+current_cast,template.production_order.final_inventory_min_t)
    d={name:getattr(template,name) for name in template.__dataclass_fields__}
    d.update(forecast_origin=geometry.isoformat(),decision_time=state.current_time,known_arrivals=known,committed_first_feed_t=first_feed,production_order=order,initial_inventory_t=opening,heats=orders,heat_candidates=tuple(candidates),
             constraints=replace(template.constraints,horizon_slots=n,candidate_step_minutes=grid),
             background_load_forecast=template.background_load_forecast[offset:],tariff_calendar=template.tariff_calendar[offset:],
             equipment_availability={a:tuple(v[offset:]) for a,v in template.equipment_availability.items()},
             operating_windows={a:tuple(v[offset:]) for a,v in template.operating_windows.items()},health_predictions=hp,optimization_mode=mode,objective_mode='cost',template=template)
    return RemainingInput(**d).validate(),dict(provenance,inventory_source='posted heat billet register minus executed rolling acknowledgements',
                                              heat_history_features=heat,health_observation_contexts=health,
                                              AUX_forecast_available_at=template.background_load_forecast[0].available_at,AUX_refreshed=False)
