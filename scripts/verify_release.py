"""Verify the lightweight public profile, without retraining or replay jobs.

The full scientific archive is a distinct explicit verification target.
"""
from pathlib import Path
import argparse,hashlib,importlib,json,re,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
TESTS=['tests/test_dashboard.py','tests/test_dashboard_ui.py','tests/test_release_packaging.py']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def verify(archive=None):
    errors=[];profile=read(ROOT/'reports/phase4_public_profile.json')
    for relative,item in profile['originals'].items():
        p=ROOT/relative
        if not p.is_file() or sha(p)!=item['sha256']:errors.append('Changed/missing original: '+relative)
    sealed=ROOT/'configs/public_release_v1_manifest.json'
    if sealed.exists():
        for relative,digest in read(sealed)['files'].items():
            p=ROOT/relative
            if not p.is_file() or sha(p)!=digest:errors.append('Changed/missing public artifact: '+relative)
    else:errors.append('Public release is not sealed')
    for name in ('supervisor','dashboard.service'):
        importlib.import_module('energy_copilot.'+name)
    from energy_copilot.dashboard.service import DashboardService
    from energy_copilot.dashboard.scenarios import SCENARIOS
    for key in SCENARIOS:
        service=DashboardService(key);service.get_impact_summary()
        p=ROOT/service.bundle['metadata']['source_episode']/'audit.jsonl'
        if not p.is_file():errors.append('Missing approval audit source: '+key)
    deck=read(ROOT/'dashboard_deck_metrics.json')
    for item in deck['metrics']:
        p=ROOT/item['source_artifact']
        if not p.is_file() or sha(p)!=item['source_sha256']:
            errors.append('Deck source mismatch: '+item['metric']);continue
        value=read(p)
        for field in item['source_field'].split('.'):value=value[field]
        if value!=item['value']:errors.append('Unsupported deck number: '+item['metric'])
    # Historical reports intentionally cite the larger archive. Require local
    # links in new primary docs; external URLs are not fetched during offline CI.
    docs=[ROOT/'README.md',ROOT/'CONTRIBUTING.md',*(ROOT/'docs').glob('*.md')]
    for p in docs:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
            if target.startswith(('http:','https:','#','mailto:')):continue
            destination=(p.parent/target.split('#')[0]).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                errors.append('Broken primary link: '+p.name+' -> '+target)
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(x in path.parts for x in ('.git','__pycache__')) or any(x.startswith('.venv') for x in path.parts):continue
        name=path.name
        if name=='.env' or (name.startswith('.env.') and name!='.env.example') or name=='secrets.toml':errors.append('Credential configuration committed: '+str(path.relative_to(ROOT)))
        if path.suffix.lower() not in ('.py','.md','.json','.yaml','.yml','.txt','.toml'):continue
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:continue
        if re.search(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9]{32,}|AKIA[A-Z0-9]{16})\b',text):errors.append('Potential credential: '+str(path.relative_to(ROOT)))
        if path.is_relative_to(ROOT/'src') and re.search(r'[CDE]:[/\\](?:Users|Projects|Python)|/home/[^/\s]+/',text):errors.append('Private runtime path: '+str(path.relative_to(ROOT)))
    if archive:
        archive=Path(archive).resolve()
        ledger=read(ROOT/'configs/phase3a_readonly_manifest.json')
        ledger.update(read(archive/'dashboard/release_v1/manifest.json')['files'])
        for relative,digest in ledger.items():
            p=archive/relative
            if not p.is_file() or sha(p)!=digest:errors.append('Archive integrity mismatch: '+relative)
    if errors:raise ValueError('\n'.join(errors))
    return dict(status='PASS',selected_originals=len(profile['originals']),demo_scenarios=len(SCENARIOS),deck_metrics=len(deck['metrics']),
                full_archive_verified=bool(archive),sealed=sealed.exists())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests',action='store_true')
    parser.add_argument('--scientific-archive',type=Path)
    args=parser.parse_args()
    try:print(json.dumps(verify(args.scientific_archive),indent=2))
    except (ValueError,KeyError,OSError) as exc:print(str(exc),file=sys.stderr);return 1
    if args.tests:return subprocess.call([sys.executable,'-m','pytest','-q',*TESTS],cwd=ROOT)
    return 0
if __name__=='__main__':raise SystemExit(main())
