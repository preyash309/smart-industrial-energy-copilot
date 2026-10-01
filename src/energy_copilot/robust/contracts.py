from dataclasses import dataclass, fields
import math
import pandas as pd
from energy_copilot.optimization.contracts import OptimizerInput, timestamp,HeatCandidate
from energy_copilot.forecast.interfaces import HeatPrediction,HealthPrediction


@dataclass(frozen=True)
class ReservePolicy:
    end_margin_min: float = 0.0
    uncertainty_buffer_fraction: float = 0.0
    minimum_buffer_min: float = 0.0

    def validate(self):
        if any(not math.isfinite(v) or v < 0 for v in (self.end_margin_min,self.uncertainty_buffer_fraction,self.minimum_buffer_min)):
            raise ValueError('Invalid reserve/buffer policy')
        return self

    def buffer(self, prediction):
        # This is additional scheduling slack, NOT a newly calibrated quantile.
        return max(self.minimum_buffer_min,self.uncertainty_buffer_fraction *
                   (prediction.duration_p90_min-prediction.duration_p50_min))


@dataclass(frozen=True)
class DurationScenario:
    name: str
    residual_min: tuple = ()
    use_upper_quantiles: bool = False
    source: str = 'published frozen prediction'


@dataclass(frozen=True)
class ExecutedHeatDecision:
    heat_id: str
    start: str
    end: str


@dataclass(frozen=True)
class ReplanState:
    current_time: str
    completed_heats: tuple
    remaining_heats: tuple
    actual_inventory_t: float
    executed_rolling: tuple
    frozen_executed_decisions: tuple
    equipment_availability: dict
    observed_recent_load: tuple = ()
    latest_health_state: tuple = ()

    def validate(self, template):
        at=pd.Timestamp(self.current_time);origin=pd.Timestamp(template.forecast_origin)
        if not origin<=at<=origin+pd.Timedelta(days=1):
            raise ValueError('Replanning time outside operating day')
        ids=[h.heat_id for h in template.heats]
        if list(self.completed_heats)+list(self.remaining_heats)!=ids:
            raise ValueError('Completed decisions cannot be reordered/rescheduled')
        if len(self.frozen_executed_decisions)!=len(self.completed_heats):raise ValueError('Missing executed heat ledger')
        if tuple(r.heat_id for r in self.frozen_executed_decisions)!=self.completed_heats:raise ValueError('Executed identities changed')
        for row in self.frozen_executed_decisions:
            if not origin<=pd.Timestamp(row.start)<pd.Timestamp(row.end)<=at:raise ValueError('Unposted/invalid executed heat')
        if len(self.executed_rolling)!=math.ceil((at-origin).total_seconds()/900):raise ValueError('Incomplete executed rolling ledger')
        if not template.constraints.inventory_min_t<=self.actual_inventory_t<=template.constraints.inventory_max_t:
            raise ValueError('Invalid observed inventory')
        if any(not math.isfinite(v) or v<0 for v in self.executed_rolling):raise ValueError('Invalid feed acknowledgement')
        return self


@dataclass(frozen=True)
class RemainingInput(OptimizerInput):
    """Successor geometry: shortened day, genuine current publication timestamps.

    Original day input is validated first; immutable physical/forecast contracts are
    inherited. Midnight-only AUX forecasts are sliced, never relabelled/refreshed.
    """
    template: OptimizerInput | None = None
    decision_time: str | None = None
    known_arrivals: tuple = ()
    committed_first_feed_t: float | None = None

    def validate(self):
        if self.template is None:raise ValueError('Original validated day input required')
        self.template.validate();base=self.template;c=self.constraints
        origin=timestamp(self.forecast_origin);begin=timestamp(base.forecast_origin)
        offset=(origin-begin).total_seconds()/900
        if offset!=int(offset) or not 0<=offset<96 or c.horizon_slots!=96-int(offset):raise ValueError('Invalid remaining horizon')
        for f in fields(c):
            if f.name not in ('horizon_slots','candidate_step_minutes') and getattr(c,f.name)!=getattr(base.constraints,f.name):
                raise ValueError('Frozen physical constraints changed: '+f.name)
        if c.candidate_step_minutes not in (1,5):raise ValueError('Unsupported successor start grid')
        if self.prediction_version!=base.prediction_version or self.prediction_schema_sha256!=base.prediction_schema_sha256 or self.expected_prediction_schema_sha256!=base.expected_prediction_schema_sha256:
            raise ValueError('Prediction version/schema changed')
        if self.optimization_mode not in ('central','conservative') or self.objective_mode not in ('cost','energy','feasibility'):
            raise ValueError('Invalid mode')
        if not self.heats or tuple(self.heats)!=tuple(base.heats[-len(self.heats):]):raise ValueError('Remaining heats must be ordered suffix')
        if not c.inventory_min_t<=self.initial_inventory_t<=c.inventory_max_t:raise ValueError('Invalid observed inventory')
        for name in ('bars_t','billets_t','final_inventory_min_t'):
            v=getattr(self.production_order,name)
            if not math.isfinite(v) or v<0:raise ValueError('Invalid remaining production requirement')
        offset=int(offset)
        decision=timestamp(self.decision_time or self.forecast_origin)
        if not origin<=decision<origin+pd.Timedelta(minutes=15):raise ValueError('Decision time/geometry mismatch')
        if len(self.known_arrivals)!=c.horizon_slots+1 or any(not math.isfinite(v) or v<0 for v in self.known_arrivals):raise ValueError('Invalid posted arrivals')
        if any(v for v in self.known_arrivals[2:]) or self.known_arrivals[0]:raise ValueError('Future known arrivals forbidden')
        completed_liquid=sum(h.liquid_t for h in base.heats)-sum(h.liquid_t for h in self.heats)
        prior_feed=base.initial_inventory_t+completed_liquid*c.cast_yield-self.known_arrivals[1]-self.initial_inventory_t
        expected_bars=max(0,base.production_order.bars_t-prior_feed*c.rolling_yield)
        expected_billets=sum(h.liquid_t for h in self.heats)*c.cast_yield+self.known_arrivals[1]
        if prior_feed<-c.tolerance or abs(self.production_order.bars_t-expected_bars)>c.tolerance or abs(self.production_order.billets_t-expected_billets)>c.tolerance or self.production_order.final_inventory_min_t!=base.production_order.final_inventory_min_t:
            raise ValueError('Remaining production/stock accounting changed')
        if self.committed_first_feed_t is not None and not 0<=self.committed_first_feed_t<=min(c.mill_capacity_tph,c.rhf_capacity_tph)*.25+c.tolerance:raise ValueError('Invalid committed current-slot feed')
        for mapping,old in ((self.equipment_availability,base.equipment_availability),(self.operating_windows,base.operating_windows)):
            if mapping!={a:tuple(v[offset:]) for a,v in old.items()}:raise ValueError('Availability/calendar altered without external input')
        if self.background_load_forecast!=base.background_load_forecast[offset:] or self.tariff_calendar!=base.tariff_calendar[offset:]:
            raise ValueError('Frozen AUX forecast/tariff changed')
        if (self.tariff_period_rates,self.tariff_version,self.tariff_source)!=(base.tariff_period_rates,base.tariff_version,base.tariff_source):raise ValueError('Tariff changed')
        seen=set();covered=set();ids={h.heat_id for h in self.heats}
        for k in self.heat_candidates:
            if not isinstance(k,HeatCandidate) or not isinstance(k.prediction,HeatPrediction):raise ValueError('Typed PredictionService heat output required')
            p=k.prediction;start=timestamp(k.start);minute=(start-origin).total_seconds()/60
            if k.candidate_id in seen or k.heat_id not in ids or p.heat_id!=k.heat_id:raise ValueError('Candidate identity mismatch')
            seen.add(k.candidate_id);covered.add(k.heat_id)
            if start<decision or not 0<=minute<c.horizon_slots*15 or minute%c.candidate_step_minutes:raise ValueError('Candidate in executed past/off grid')
            if p.practice_mode not in c.supported_practices:raise ValueError('Unknown practice')
            _prediction(p,self)
            for prefix,unit in [('energy','kWh'),('duration','min')]:
                q=[getattr(p,f'{prefix}_p{x}_{unit}') for x in (10,50,90)]
                if any(not math.isfinite(v) or v<=0 for v in q) or q!=sorted(q):raise ValueError('Invalid quantiles')
            if abs(p.SEC_p50-p.energy_p50_kWh/next(h.liquid_t for h in self.heats if h.heat_id==k.heat_id))>c.tolerance:raise ValueError('Invalid SEC')
        if covered!=ids:raise ValueError('Missing remaining heat prediction')
        for p in self.health_predictions:
            if not isinstance(p,HealthPrediction) or p.asset_id not in ('MILL_01','PMP_01') or p.horizon_hours!=24:raise ValueError('Invalid health prediction contract')
            _prediction(p,self)
            if any(v is None or not math.isfinite(v) or not 0<=v<=1 for v in (p.failure_probability,p.calibrated_probability)):raise ValueError('Invalid health probability')
        return self


def _prediction(p,inp):
    if p.status!='model' or not p.usable_for_constraints or p.model_version!=inp.prediction_version:
        raise ValueError('Unsafe/incompatible prediction')
    if timestamp(p.available_at)>timestamp(getattr(inp,'decision_time',None) or inp.forecast_origin):raise ValueError('Future prediction')
