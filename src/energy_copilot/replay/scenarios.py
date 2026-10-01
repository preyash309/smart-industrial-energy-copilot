"""Explicit exogenous identity, including sensor tapes, before decisions."""
import hashlib
import numpy as np
from energy_copilot.common import values,canonical_hash
from energy_copilot.sim.scenario import scenario


def scenario_proof(config, seed, days):
    tape=scenario(values(config),seed,days)
    def digest(x):
        if isinstance(x,np.ndarray):
            return hashlib.sha256(str(x.dtype).encode()+str(x.shape).encode()+x.tobytes()).hexdigest()
        if isinstance(x,dict):return {k:digest(v) for k,v in x.items()}
        return canonical_hash(x)
    return dict(seed=seed,days=days,scenario_sha256=tape['hash'],
                component_hashes={k:digest(v) for k,v in tape.items() if k!='hash'},
                generated_before_decisions=True,horizon_must_match=True)

