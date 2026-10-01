"""Uncertainty descriptions use development residuals, never a replay seed's truth."""
import math
from .contracts import DurationScenario


def scenario_coefficients(candidate, inp, scenario, position):
    p=candidate.prediction;upper=scenario.use_upper_quantiles
    q=90 if upper else (50 if inp.optimization_mode=='central' else 90)
    energy=getattr(p,f'energy_p{q}_kWh')
    nominal=getattr(p,f'duration_p{q}_min')
    residual=scenario.residual_min[position] if scenario.residual_min else 0.0
    if not math.isfinite(residual):raise ValueError('Invalid scenario residual')
    # Residuals are against p50, so taking max prevents adding residuals atop p90.
    duration=max(nominal,p.duration_p50_min+residual,
                 energy/inp.constraints.ratings_kW['IF_01']*60+inp.constraints.if_nonpowered_min)
    return energy,duration


def make_scenarios(calibration, heat_ids):
    indices=[int(h.rsplit('H',1)[1]) for h in heat_ids]
    vectors=calibration['selected_day_residual_vectors']
    result=[DurationScenario('central'),DurationScenario('marginal_p90',use_upper_quantiles=True)]
    for i,vector in enumerate(vectors):
        result.append(DurationScenario(f'whole_development_day_{i}',tuple(vector[k] for k in indices),
                                       source='fresh development whole-day public-duration residual vector'))
    # Stress one declared heat, rather than combining all severe outcomes.
    v=[0.0]*len(indices);v[0]=calibration['positive_residual_p95_min']
    result.append(DurationScenario('next_heat_severe',tuple(v),source='fresh development positive residual p95; next unexecuted heat'))
    return tuple(result)

