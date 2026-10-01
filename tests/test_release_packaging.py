"""Public-profile checks are additions; original scientific tests stay intact."""
import importlib.util,json
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1]

def test_public_profile_and_deck_source_closure():
    spec=importlib.util.spec_from_file_location('release_check',ROOT/'scripts/verify_release.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.verify()
    assert result['status']=='PASS' and result['demo_scenarios']==4 and result['deck_metrics']==30

def test_original_tests_are_retained():
    originals=json.loads((ROOT/'reports/phase4_public_profile.json').read_text())['originals']
    assert any('test_optimizer' in p for p in originals)
    assert 'tests/test_phase2f_maintenance.py' in originals
    assert all((ROOT/p).is_file() for p in originals if p.startswith('tests/'))

def test_minimal_example_uses_checked_demo():
    result=subprocess.run([sys.executable,str(ROOT/'examples/demo_decision.py')],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    packet=json.loads(result.stdout)
    assert packet['scope']=='PRECOMPUTED VERIFIED DEMO'
    assert packet['operator_status']=='VERIFIED'
    assert packet['replay']['physically_valid'] is True
