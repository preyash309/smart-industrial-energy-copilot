"""Public solver-independent planning contracts. No table/model artifact loaders."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import math
from energy_copilot.forecast.interfaces import HeatPrediction, LoadPrediction, HealthPrediction

ASSETS=('IF_01','RHF_01','MILL_01','PMP_01','CMP_01')


def timestamp(value):
    if not isinstance(value,str): raise ValueError('Timestamp must be a local ISO string')
    try: t=datetime.fromisoformat(value)
    except (TypeError,ValueError): raise ValueError('Invalid timestamp') from None
    if t.tzinfo is not None: raise ValueError('Use declared local naive timestamps')
    return t


def finite(value,name,minimum=0):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<minimum:
        raise ValueError(f'Invalid {name}')


@dataclass(frozen=True)
class ProductionOrder:
    bars_t: float
    billets_t: float
    final_inventory_min_t: float


@dataclass(frozen=True)
class HeatOrder:
    heat_id: str
    liquid_t: float


@dataclass(frozen=True)
class HeatCandidate:
    candidate_id: str
    heat_id: str
    start: str
    prediction: HeatPrediction


@dataclass(frozen=True)
class TariffSlot:
    interval_start: str
    interval_end: str
    period: str
    Rs_per_kWh: float


@dataclass(frozen=True)
class OperatingConstraints:
    slot_minutes: int
    horizon_slots: int
    candidate_step_minutes: int
    demand_limit_kVA: float
    inventory_min_t: float
    inventory_max_t: float
    cast_yield: float
    rolling_yield: float
    melt_yield: float
    mill_capacity_tph: float
    rhf_capacity_tph: float
    mill_SEC_kWh_per_t_bar: float
    if_nonpowered_min: float
    rhf_temperature_C: float
    rhf_min_C: float
    rhf_max_C: float
    ratings_kW: dict
    power_factors: dict
    compressor_loaded_kW: float
    compressor_idle_kW: float
    supported_practices: tuple
    sec_target_kWh_per_t: float | None
    tolerance: float
    solver_options: dict


@dataclass(frozen=True)
class OptimizerInput:
    forecast_origin: str
    production_order: ProductionOrder
    initial_inventory_t: float
    heats: tuple[HeatOrder,...]
    heat_candidates: tuple[HeatCandidate,...]
    background_load_forecast: tuple[LoadPrediction,...]
    equipment_availability: dict
    operating_windows: dict
    tariff_calendar: tuple[TariffSlot,...]
    tariff_period_rates: dict
    tariff_version: str
    tariff_source: str
    constraints: OperatingConstraints
    prediction_version: str
    prediction_schema_sha256: str
    expected_prediction_schema_sha256: str
    health_predictions: tuple[HealthPrediction,...]=()
    optimization_mode: str='central'
    objective_mode: str='feasibility'

    def validate(self):
        origin=timestamp(self.forecast_origin); c=self.constraints
        if origin.time()!=datetime.min.time(): raise ValueError('Frozen forecasting contract requires midnight origin')
        if self.optimization_mode not in ('central','conservative'): raise ValueError('Unknown uncertainty mode')
        if self.objective_mode not in ('feasibility','energy','cost'): raise ValueError('Unknown objective')
        if type(c.slot_minutes) is not int or type(c.horizon_slots) is not int or c.slot_minutes!=15 or c.horizon_slots!=96: raise ValueError('Only 96 x 15-minute horizon supported')
        if not isinstance(c.candidate_step_minutes,int) or c.candidate_step_minutes<=0 or c.slot_minutes%c.candidate_step_minutes:
            raise ValueError('Start grid must divide accounting slot')
        if not self.prediction_version or self.prediction_schema_sha256!=self.expected_prediction_schema_sha256 or len(self.prediction_schema_sha256)!=64:
            raise ValueError('Prediction schema/version mismatch')
        for name in ('demand_limit_kVA','inventory_min_t','inventory_max_t','mill_capacity_tph','rhf_capacity_tph','mill_SEC_kWh_per_t_bar','if_nonpowered_min','tolerance'):
            finite(getattr(c,name),name)
        if c.demand_limit_kVA<=0 or c.tolerance<=0 or c.inventory_min_t>=c.inventory_max_t: raise ValueError('Invalid physical bounds')
        for name in ('cast_yield','rolling_yield','melt_yield'):
            finite(getattr(c,name),name)
            if not 0<getattr(c,name)<=1: raise ValueError('Invalid yield')
        for v in (c.rhf_temperature_C,c.rhf_min_C,c.rhf_max_C): finite(v,'RHF temperature')
        if not c.rhf_min_C<=c.rhf_temperature_C<=c.rhf_max_C: raise ValueError('Unqualified RHF temperature')
        if set(c.ratings_kW)!=set(ASSETS) or set(c.power_factors)!=set(ASSETS+('AUX',)): raise ValueError('Unknown/missing asset ratings/PF')
        for a in ASSETS: finite(c.ratings_kW[a],a+' rating',1e-12)
        for a,pf in c.power_factors.items():
            finite(pf,a+' PF')
            if not 0<pf<=1: raise ValueError('Invalid PF')
        for v in (c.compressor_idle_kW,c.compressor_loaded_kW): finite(v,'compressor duty')
        if not c.compressor_idle_kW<=c.compressor_loaded_kW<=c.ratings_kW['CMP_01']: raise ValueError('Compressor above nameplate')
        if c.sec_target_kWh_per_t is not None: finite(c.sec_target_kWh_per_t,'SEC target',1e-12)
        options=c.solver_options
        if set(options)!={'library','pyomo_version','highspy_version','threads','seed','time_limit_seconds','relative_gap','absolute_gap'}: raise ValueError('Solver option schema mismatch')
        if options['library']!='pyomo.appsi.highs' or options['threads']!=1 or type(options['threads']) is not int: raise ValueError('Only deterministic serial HiGHS supported')
        if type(options['seed']) is not int or options['seed']<0: raise ValueError('Invalid solver seed')
        for name in ('time_limit_seconds','relative_gap','absolute_gap'): finite(options[name],name)
        if options['time_limit_seconds']<=0 or options['relative_gap']!=0: raise ValueError('Invalid solver limit/gap')
        finite(self.initial_inventory_t,'initial inventory')
        if not c.inventory_min_t<=self.initial_inventory_t<=c.inventory_max_t: raise ValueError('Invalid initial inventory')
        for name,value in asdict(self.production_order).items(): finite(value,name)
        if not c.inventory_min_t<=self.production_order.final_inventory_min_t<=c.inventory_max_t: raise ValueError('Invalid closing reserve')
        if not self.heats or len({h.heat_id for h in self.heats})!=len(self.heats): raise ValueError('Empty/duplicate heat order')
        ids={h.heat_id for h in self.heats}
        for h in self.heats:
            if not isinstance(h.heat_id,str) or not h.heat_id: raise ValueError('Invalid heat ID')
            finite(h.liquid_t,'liquid tonnes',1e-12)
        for mapping in (self.equipment_availability,self.operating_windows):
            if set(mapping)!=set(ASSETS): raise ValueError('Unknown/missing availability assets')
            for mask in mapping.values():
                if len(mask)!=c.horizon_slots or any(type(v) is not bool for v in mask): raise ValueError('Invalid availability/calendar mask')
        seen=set();covered=set()
        liquid={h.heat_id:h.liquid_t for h in self.heats}
        for k in self.heat_candidates:
            if not isinstance(k,HeatCandidate) or not isinstance(k.prediction,HeatPrediction): raise ValueError('Typed heat predictions required')
            p=k.prediction
            if not isinstance(k.candidate_id,str) or not k.candidate_id or k.candidate_id in seen or k.heat_id not in ids or p.heat_id!=k.heat_id: raise ValueError('Candidate identity mismatch')
            seen.add(k.candidate_id); covered.add(k.heat_id)
            if p.practice_mode not in c.supported_practices: raise ValueError('Unsupported practice mode')
            start=timestamp(k.start); offset=(start-origin).total_seconds()/60
            if not 0<=offset<c.slot_minutes*c.horizon_slots or abs(offset/c.candidate_step_minutes-round(offset/c.candidate_step_minutes))>c.tolerance:
                raise ValueError('Candidate start outside valid grid/horizon')
            validate_prediction(p,self)
            for prefix,suffix in [('energy','kWh'),('duration','min')]:
                q=[getattr(p,f'{prefix}_p{i}_{suffix}') for i in (10,50,90)]
                for v in q: finite(v,prefix,1e-12)
                if q!=sorted(q): raise ValueError('Quantile ordering violation')
            finite(p.SEC_p50,'SEC')
            if abs(p.SEC_p50-p.energy_p50_kWh/liquid[k.heat_id])>c.tolerance: raise ValueError('Inconsistent predicted SEC')
        if covered!=ids: raise ValueError('Missing heat predictions')
        n=c.horizon_slots
        if len(self.background_load_forecast)!=n or len(self.tariff_calendar)!=n: raise ValueError('Missing load/tariff slots')
        if not self.tariff_version or not self.tariff_source or not self.tariff_period_rates: raise ValueError('Unversioned tariff')
        for v in self.tariff_period_rates.values(): finite(v,'tariff rate')
        for t,(p,tariff) in enumerate(zip(self.background_load_forecast,self.tariff_calendar)):
            if not isinstance(p,LoadPrediction) or not isinstance(tariff,TariffSlot): raise ValueError('Typed load/tariff required')
            validate_prediction(p,self)
            start=origin+timedelta(minutes=t*c.slot_minutes);end=start+timedelta(minutes=c.slot_minutes)
            if type(p.horizon_slot) is not int or (timestamp(p.interval_start),timestamp(p.interval_end),p.horizon_slot)!=(start,end,t+1): raise ValueError('Misaligned load forecast')
            if tuple(p.components)!=('AUX',): raise ValueError('AUX only: MAIN would double count controlled loads')
            q=[p.load_p10_kW,p.load_p50_kW,p.load_p90_kW]
            for v in q: finite(v,'AUX forecast')
            if q!=sorted(q): raise ValueError('Load quantile order')
            if (timestamp(tariff.interval_start),timestamp(tariff.interval_end))!=(start,end): raise ValueError('Misaligned tariff')
            if tariff.period not in self.tariff_period_rates: raise ValueError('Unknown tariff period')
            if tariff.Rs_per_kWh!=self.tariff_period_rates[tariff.period]: raise ValueError('Tariff period/rate mismatch')
        for p in self.health_predictions:
            if not isinstance(p,HealthPrediction) or p.asset_id not in ('MILL_01','PMP_01') or p.horizon_hours!=24: raise ValueError('Unsupported health prediction')
            validate_prediction(p,self)
            for v in (p.failure_probability,p.calibrated_probability):
                if v is None: raise ValueError('Uncalibrated health prediction')
                finite(v,'health probability')
                if v>1: raise ValueError('Probability above one')
        return self


def validate_prediction(p,inp):
    if p.model_version!=inp.prediction_version: raise ValueError('Incompatible model version')
    if p.usable_for_constraints is not True or p.status!='model': raise ValueError('Unsafe fallback prediction')
    if timestamp(p.available_at)>timestamp(inp.forecast_origin): raise ValueError('Prediction published after origin')


@dataclass(frozen=True)
class OptimizerResult:
    status: str
    releasable: bool
    optimization_mode: str
    objective_mode: str
    schedule: tuple=()
    predicted_metrics: dict=field(default_factory=dict)
    inventory_trajectory: tuple=()
    load_trajectory: tuple=()
    active_constraints: dict=field(default_factory=dict)
    health_context: tuple=()
    assumptions: tuple=()
    explanation_data: tuple=()
    solver_status: dict=field(default_factory=dict)
    checker: dict=field(default_factory=dict)
    reason: str | None=None
    forecast_origin: str | None=None

    def to_dict(self): return asdict(self)


def input_from_dict(node):
    """Rehydrate exact public JSON snapshot; unknown fields fail closed."""
    d=dict(node)
    d['production_order']=ProductionOrder(**d['production_order'])
    d['heats']=tuple(HeatOrder(**h) for h in d['heats'])
    d['heat_candidates']=tuple(HeatCandidate(**dict(k,prediction=HeatPrediction(**k['prediction']))) for k in d['heat_candidates'])
    d['background_load_forecast']=tuple(LoadPrediction(**dict(p,components=tuple(p['components']))) for p in d['background_load_forecast'])
    d['health_predictions']=tuple(HealthPrediction(**p) for p in d['health_predictions'])
    d['tariff_calendar']=tuple(TariffSlot(**t) for t in d['tariff_calendar'])
    d['equipment_availability']={a:tuple(mask) for a,mask in d['equipment_availability'].items()}
    d['operating_windows']={a:tuple(mask) for a,mask in d['operating_windows'].items()}
    d['constraints']=OperatingConstraints(**dict(d['constraints'],supported_practices=tuple(d['constraints']['supported_practices'])))
    return OptimizerInput(**d).validate()
