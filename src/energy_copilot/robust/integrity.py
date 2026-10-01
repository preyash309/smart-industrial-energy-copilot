"""Upstream evidence hashes and development/final-evaluation firewalls."""
from pathlib import Path
import json
from energy_copilot.common import sha256,write_json,canonical_hash

MANIFEST=Path('configs/phase2e_readonly_manifest.json')


def protect_upstream():
    if MANIFEST.exists():return verify_upstream()
    h=json.loads(Path('configs/phase2d_readonly_manifest.json').read_text())
    release=Path('replay/optimizer_v1/release_manifest.json');r=json.loads(release.read_text())
    h.update({'replay/optimizer_v1/'+p:d for p,d in r['hashes'].items()});h.update(r['reports'])
    code=json.loads(Path('replay/optimizer_v1/code_manifest.json').read_text())
    h.update(code.get('hashes',code))
    for p in ('configs/phase2d_readonly_manifest.json',str(release),'docs/phase2d_usage.md','docs/phase2d_changelog.md'):
        h[p]=sha256(p)
    changed=[p for p,d in h.items() if not Path(p).is_file() or sha256(p)!=d]
    if changed:raise RuntimeError('Existing frozen evidence changed: '+str(changed))
    write_json(MANIFEST,h);return verify_upstream()


def verify_upstream():
    h=json.loads(MANIFEST.read_text());changed=[p for p,d in h.items() if not Path(p).is_file() or sha256(p)!=d]
    if changed:raise RuntimeError('Frozen upstream changed: '+str(changed))
    return dict(status='PASS',protected_files=len(h))


def validate_split(split):
    groups=[set(split[k]) for k in ('development','validation','final_regression')]
    if any(groups[i]&groups[j] for i in range(3) for j in range(i)):raise ValueError('Seed leakage between splits')
    if groups[2]!=set(range(201,211)):raise ValueError('Frozen final evaluation set changed')
    if (groups[0]|groups[1])&set(split['upstream_used_seeds']):raise ValueError('Fresh seeds overlap upstream')
    return True


def require_development(seed,split):
    validate_split(split)
    if seed not in split['development']:raise ValueError('Calibration may use development seeds only')


def freeze_policy(path,policy,calibration,split):
    validate_split(split)
    node=dict(policy=policy,calibration_sha256=canonical_hash(calibration),split_sha256=canonical_hash(split),
              config_sha256=sha256('configs/robustness_v1.yaml'),
              source_hashes={str(p).replace('\\','/'):sha256(p) for p in sorted(Path('src/energy_copilot/robust').glob('*.py'))},
              final_evaluation_used_for_selection=False)
    node['design_sha256']=canonical_hash(node);write_json(path,node);return node
