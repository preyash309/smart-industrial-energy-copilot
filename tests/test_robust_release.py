"""Acceptance checks over every retained final attempt; no success threshold fitting."""
from pathlib import Path
import json
import pandas as pd
import pytest
from energy_copilot.common import sha256
from energy_copilot.robust.integrity import verify_upstream,validate_split

ROOT=Path('replay/robustness_v1')
pytestmark=pytest.mark.skipif(not (ROOT/'final_regression_results.json').exists(),reason='Run the frozen final evaluation first')


def rows():return json.loads((ROOT/'final_regression_results.json').read_text())


def test_all_attempts_remain_in_denominator():
    r=rows();assert len(r)==50
    assert {(x['seed'],x['strategy']) for x in r}=={(s,e) for s in range(201,211) for e in ('E0','E1','E2','E3','E4')}
    assert all(x['result']['retained'] for x in r)


def test_every_accepted_trace_has_independent_physical_and_matching_checks():
    for row in rows():
        e=row['result']
        if e['status']=='physically_valid':
            assert e['verification']['feasible'] and not any(e['verification']['checks'].values())
            assert e['matched_conditions']['status']=='PASS'
            assert e['realized_metrics']['bar_t']==pytest.approx(118.56)
            assert e['realized_metrics']['peak_piecewise_kVA']<=7000
            assert e['realized_metrics']['inventory_min_t']>=-1e-7
            assert e['realized_metrics']['inventory_max_t']<=200
        else:assert e['realized_metrics'] is None


def test_all_e0_plan_and_physical_regressions():
    for seed in range(201,211):
        r=ROOT/'final_regression'/f'seed_{seed}';checks=json.loads((r/'E0_regression.json').read_text())
        assert all(all(v.values()) for v in checks.values())
        for strategy,key in [('E0','S3'),('E1','conservative_synthetic')]:
            old=Path('replay/optimizer_v1/evaluation')/f'seed_{seed}'/'predicted_plans'/f'{key}.json'
            assert sha256(r/strategy/'initial_plan.json')==sha256(old)


def test_final_seeds_never_calibrate_uncertainty():
    split=json.loads((ROOT/'split_manifest.json').read_text());assert validate_split(split)
    cal=json.loads((ROOT/'duration_calibration.json').read_text())
    assert cal['source_seeds']==split['development']
    assert not set(cal['source_seeds'])&set(range(201,211))
    assert verify_upstream()['status']=='PASS'


def test_every_replan_uses_legally_posted_features_and_preserves_execution():
    for seed in range(201,211):
        for strategy in ('E3','E4'):
            root=ROOT/'final_regression'/f'seed_{seed}'/strategy;previous=None
            paths=[root/'initial_plan.json',*sorted(root.glob('replan_step*.json'))]
            for path in paths:
                d=json.loads(path.read_text());at=pd.Timestamp(d['current_time']);state=d['state'];info=d['available_information']
                for posting in info['heat_history_features']['available_at'].values():assert pd.Timestamp(posting)<=at
                for health in info['health_observation_contexts']:
                    for posting in health['available_at'].values():assert pd.Timestamp(posting)<=at
                for heat in state['frozen_executed_decisions']:assert pd.Timestamp(heat['end'])<=at
                for row in state['observed_recent_load']:assert pd.Timestamp(row['interval_end'])<=at
                assert all(pd.Timestamp(h['start'])>=at for h in d['selected_schedule'])
                if previous:
                    assert state['executed_rolling'][:len(previous['executed_rolling'])]==previous['executed_rolling']
                    assert state['frozen_executed_decisions'][:len(previous['frozen_executed_decisions'])]==previous['frozen_executed_decisions']
                previous=state


def test_adaptive_byte_reproduction():
    r=json.loads((ROOT/'adaptive_reproducibility.json').read_text());assert r['status']=='PASS' and all(r['checks'].values())
