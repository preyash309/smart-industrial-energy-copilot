from .contracts import ROOT,read_json,file_hash,validate_bundle,DashboardError
from .scenarios import scenario

def load_demo(key):
    scenario(key);base=ROOT/'dashboard/evidence_v1';manifest=read_json(base/'manifest.json')
    relative=key+'/bundle.json'
    if relative not in manifest['files'] or file_hash(base/relative)!=manifest['files'][relative]:
        raise DashboardError('Demo evidence integrity check failed. Recommendation withheld.')
    return validate_bundle(read_json(base/relative))
