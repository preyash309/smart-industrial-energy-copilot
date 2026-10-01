"""Deterministic constraint and objective evidence; no language model calls."""
from .contracts import timestamp


def explanation_data(inp,result,baseline=None):
    if not result.releasable:return (dict(kind='infeasible',reason=result.reason,solver=result.solver_status),)
    base={r['heat_id']:r for r in baseline.schedule} if baseline is not None and baseline.releasable else {}
    def local_cost(row):
        c=inp.constraints;origin=timestamp(inp.forecast_origin)
        # Use frozen duration, avoiding microsecond serialization rounding.
        start=(timestamp(row['start'])-origin).total_seconds()/60
        end=start+row['selected_duration_min']
        lo=end-row['selected_energy_kWh']/c.ratings_kW['IF_01']*60
        return sum(max(0,min(end,(t+1)*c.slot_minutes)-max(lo,t*c.slot_minutes))/60*c.ratings_kW['IF_01']*rate.Rs_per_kWh for t,rate in enumerate(inp.tariff_calendar))
    evidence=[]
    for row in result.schedule:
        old=base.get(row['heat_id'])
        evidence.append(dict(heat_id=row['heat_id'],selected_start=row['start'],selected_practice=row['selected_practice'],
            selected_IF_energy_cost_Rs=local_cost(row),baseline_start=old['start'] if old else None,
            baseline_IF_energy_cost_Rs=local_cost(old) if old else None,
            predicted_IF_cost_delta_Rs=local_cost(row)-local_cost(old) if old else None,
            start_delta_minutes=(timestamp(row['start'])-timestamp(old['start'])).total_seconds()/60 if old else None,
            predicted_energy_delta_kWh=row['selected_energy_kWh']-old['selected_energy_kWh'] if old else None,
            objective=inp.objective_mode,production_met=result.checker['feasible'],minimum_inventory_t=result.predicted_metrics['inventory_min_t'],
            minimum_demand_slack_kVA=result.active_constraints['min_demand_slack_kVA'],
            limitation='Joint optimal-plan accounting evidence, not proof of a unique reason or an isolated counterfactual. Synthetic practice is not field-qualified.'))
    return tuple(evidence)
