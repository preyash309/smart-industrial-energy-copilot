"""Proof of deterministic history recreation. Hidden state is evaluation-only."""
import hashlib
from io import BytesIO
import pandas as pd
from energy_copilot.common import canonical_hash

TABLES=('readings','heats','production','events','latent_truth','latent_heats')


def frame_hash(frame):
    buf=BytesIO();frame.reset_index(drop=True).to_parquet(buf,index=False)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def before_origin(sim, origin):
    origin=pd.Timestamp(origin); frames={}
    for name in TABLES:
        x=getattr(sim,name)
        if name in ('readings','latent_truth'): x=x[x.timestamp<origin]
        elif name in ('heats','latent_heats'): x=x[x.end<=origin]
        elif name=='production':
            ends=pd.to_datetime(x.date)+pd.to_timedelta((x['shift'].astype(int)+1)*8,unit='h')
            x=x[ends<=origin]
        else:
            x=x[x.start<origin].copy()
            x['end']=x.end.clip(upper=origin)
            x['duration_min']=(x.end-x.start).dt.total_seconds()/60
        frames[name]=frame_hash(x)
    # No unrepresented runtime/thermal state is invented. Wear is calendar-driven;
    # AUX/RHF temperature algebraic; no random state consumed by decisions.
    main=sim.latent_truth.query("asset_id == 'MAIN' and timestamp < @origin").iloc[-1]
    return dict(method='deterministic full-horizon recreation from initial state',
                origin=origin.isoformat(),prefix_hashes=frames,inventory_t=float(main.yard_stock_t),
                represented_state='inventory; calendar wear/fault/repair tape; algebraic temperature/flow; identical observations and heat history',
                unrepresented_state='no persistent thermal dynamics or runtime-driven wear counters in V1.1')


def match_manifest(baseline, branch, controls, inp, scenario_proof):
    a=before_origin(baseline,controls.origin);b=before_origin(branch,controls.origin)
    same=a==b
    scenario_same=baseline.scenario_manifest['scenario_sha256']==branch.scenario_manifest['scenario_sha256']
    return dict(status='PASS' if same and scenario_same else 'FAIL',history_identical=same,
        scenario_identical=scenario_same,origin_state=a,branch_origin_state=b,
        scenario=scenario_proof,controls=controls.to_dict(),controls_sha256=controls.sha256,
        production_order_sha256=canonical_hash(inp.production_order.__dict__),
        tariff_sha256=canonical_hash([t.__dict__ for t in inp.tariff_calendar]),
        opening_inventory_matches=abs(a['inventory_t']-inp.initial_inventory_t)<inp.constraints.tolerance,
        only_declared_controls='heat starts, day-scoped uniform practice and exact rolling feed; no fault suppression, scenario or measurement changes')

