"""Reporting gates; no solver, policy, or simulator parameter changes."""
import json
import pytest
from scripts.phase2f_validation import distribution, paired_statistics, terminal_cause, DISPOSITIONS


def test_empty_distribution_is_not_zero_outcome():
    assert distribution([])==dict(n=0,mean=None,median=None,min=None,max=None)


def test_paired_deltas_not_difference_of_unmatched_means():
    def metrics(energy,cost,downtime,preventive):
        return dict(total_kWh=energy,IF_SEC_kWh_per_t=energy/10,plant_kWh_per_t_bars=energy/8,
            physical_evaluation_tariff_cost_Rs=cost,peak_piecewise_kVA=100,bar_t=8,billet_t=9,
            final_inventory_t=50,inventory_min_t=1,inventory_max_t=50,downtime_hours={'MILL_01':downtime},
            _preventive_hours=preventive)
    pairs=[(metrics(100,1000,1,0),metrics(90,1010,0,.25)),
           (metrics(200,2000,0,0),metrics(210,1990,0,.25))]
    s=paired_statistics(pairs)
    assert s['total_kWh']['delta']['mean']==0
    assert s['total_kWh']['percent_delta']['mean']==pytest.approx(-2.5)
    assert s['corrective_asset_downtime_hours']['delta']['mean']==-.5
    assert s['preventive_asset_downtime_hours']['delta']['mean']==.25
    assert s['total_asset_downtime_hours']['delta']['mean']==-.25


def test_solver_limit_is_not_proven_infeasibility(tmp_path):
    (tmp_path/'initial_plan.json').write_text(json.dumps(dict(status='solver_limit')))
    cause,status,limitation=terminal_cause(tmp_path,dict(reason='No feasible maintenance continuation at feasibility',failure_class='solver_infeasibility'))
    assert cause=='solver_limit_no_accepted_continuation'
    assert status=='solver_limit' and 'not proved' in limitation


def test_end_of_day_is_not_automatically_maintenance_fault(tmp_path):
    (tmp_path/'initial_plan.json').write_text(json.dumps(dict(status='optimal')))
    cause,_,limitation=terminal_cause(tmp_path,dict(reason='Heat cannot complete daily target within working day'))
    assert cause=='end_of_day_overrun'
    assert 'not automatically maintenance' in limitation


def test_recommendation_terminal_enum():
    assert DISPOSITIONS=={'executed','replaced_by_replan','cancelled','infeasible','not_selected','run_aborted_before_execution'}
