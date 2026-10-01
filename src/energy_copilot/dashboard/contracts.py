from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import get_type_hints,get_origin,get_args,Union
import types,json,hashlib

ROOT=Path(__file__).resolve().parents[3]
class DashboardError(ValueError):pass

def read_json(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):raise DashboardError('Evidence is unavailable or invalid. Recommendation withheld.') from None

def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def protect():
    m=read_json(ROOT/'configs/phase3a_readonly_manifest.json')
    bad=[p for p,h in m.items() if not (ROOT/p).is_file() or file_hash(ROOT/p)!=h]
    if bad:raise DashboardError('Protected backend integrity check failed. Live analysis unavailable.')
    return len(m)

def typed(cls,node):
    """Rehydrate exact frozen DTOs, never arbitrary classes from incoming data."""
    if node is None:return None
    origin=get_origin(cls);args=get_args(cls)
    if origin in (Union,types.UnionType):
        return typed(next(x for x in args if x is not type(None)),node)
    if origin is tuple:
        return tuple(typed(args[0] if len(args)==2 and args[1] is Ellipsis else args[i],v) for i,v in enumerate(node))
    if hasattr(cls,'__dataclass_fields__'):
        hints=get_type_hints(cls)
        if set(node)!=set(cls.__dataclass_fields__):raise DashboardError('Decision schema mismatch.')
        return cls(**{k:typed(hints[k],v) for k,v in node.items()})
    return node

def validate_bundle(bundle):
    m=bundle['metadata'];p=bundle['packet'];origin=datetime.fromisoformat(m['origin'])
    from .scenarios import scenario
    expected=scenario(m['scenario'])
    if (m['seed'],m['day'])!=(expected['seed'],expected['day']):raise DashboardError('Mixed seed/day evidence rejected.')
    if p['predictions']['model_version']!='forecast_v1' or p['predictions']['schema_sha256']!=file_hash(ROOT/'models/phase2b_v1/prediction_schema.yaml'):
        raise DashboardError('Frozen prediction version mismatch.')
    from datetime import timedelta
    for posted in (p['snapshot']['last_posted_at'],p['predictions']['available_at']):
        age=origin-datetime.fromisoformat(posted)
        if not timedelta(0)<=age<=timedelta(minutes=30):raise DashboardError('Stale or future evidence. Recommendation withheld.')
    if p['timestamp']!=m['origin'] or p['snapshot']['snapshot_id']!=m['snapshot_id']:
        raise DashboardError('Mixed scenario evidence rejected.')
    for s in (p.get('predictions'),p.get('optimizer_plan')):
        if s and s['snapshot_id']!=m['snapshot_id']:raise DashboardError('Mixed snapshot evidence rejected.')
    for o in p['snapshot']['observations']:
        if datetime.fromisoformat(o['available_at'])>origin:raise DashboardError('Future observation rejected.')
    for h in bundle.get('observed_history',[]):
        if datetime.fromisoformat(h['available_at'])>origin:raise DashboardError('Future history rejected.')
    plan=p.get('optimizer_plan');r=p.get('replay_outcome');check=p.get('independent_check')
    if r and plan and r['schedule_id']!=plan['schedule_id']:raise DashboardError('Replay/schedule mismatch.')
    if p['outcome'] in ('VERIFIED_RECOMMENDATION','VERIFIED_ANALYSIS'):
        if not(plan and plan['optimizer_feasible'] and r and r['physically_valid'] and r['production_complete'] and check and check['passed'] and check['checks'] and all(v is True for _,v in check['checks'])
            and check['schedule_id']==plan['schedule_id'] and check['replay_id']==r['replay_id']):
            raise DashboardError('Unverified plan cannot be presented as verified.')
    if bundle['schedule']['schedule_id']!=plan['schedule_id']:raise DashboardError('Schedule bundle mismatch.')
    return bundle
