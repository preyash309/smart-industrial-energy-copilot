"""Fail-closed translation of checked optimizer plans into physical controls."""
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import pandas as pd
from energy_copilot.common import values, canonical_hash
from energy_copilot.optimization.checker import check_schedule


@dataclass(frozen=True)
class ReplayControls:
    schedule: dict
    practice_by_day: dict
    rolling_dispatch: dict
    scope: str
    origin: str
    end: str

    def to_dict(self): return asdict(self)

    @property
    def sha256(self): return canonical_hash(self.to_dict())


def adapt_plan(inp, result, plant_config, *, rolling_policy='exact'):
    inp.validate()
    if not result.releasable or not check_schedule(inp, result)['feasible']:
        raise ValueError('Unreleased or invalid predicted plan')
    if rolling_policy not in ('exact', 'reference_partial'):
        raise ValueError('Rolling policy must be explicit')
    c=values(plant_config); origin=pd.Timestamp(inp.forecast_origin)
    end=origin+pd.Timedelta(minutes=inp.constraints.slot_minutes*inp.constraints.horizon_slots)
    day=(origin-pd.Timestamp(c['start'])).days
    if origin!=origin.normalize() or end-origin!=pd.Timedelta(days=1):
        raise ValueError('Replay requires one midnight-to-midnight day')
    modes={r['selected_practice'] for r in result.schedule}
    if len(modes)!=1: raise ValueError('Mixed per-heat practice is unsupported; never approximate')
    mode=next(iter(modes))
    if mode not in ('normal','practice_loss_40'): raise ValueError('Unsupported practice')
    schedule={r['heat_id']:r['start'] for r in result.schedule}
    # Preserve exact ISO timestamps; only selected starts become physical controls.
    slots_per_day=1440//c['clock_minutes']
    dispatch={day*slots_per_day+i:float(r['rolling_billet_t']) for i,r in enumerate(result.load_trajectory)} if rolling_policy=='exact' else {}
    contract=json.loads(Path('models/phase2b_v1/prediction_contract.json').read_text())
    practice={day:contract['practice_modes'][mode]['practice_loss_kWh_t']} if mode!='normal' else {}
    return ReplayControls(schedule,practice,dispatch,
        'exact heat/practice/rolling controls' if rolling_policy=='exact' else 'heat-schedule replay only; original rolling retained',
        origin.isoformat(),end.isoformat())
