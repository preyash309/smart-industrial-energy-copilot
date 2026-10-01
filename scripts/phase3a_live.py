"""UI-owned worker; calls unchanged G0 stack and reports actual tool stages."""
from pathlib import Path
import argparse,json,sys
from energy_copilot.dashboard.contracts import ROOT,protect
from energy_copilot.dashboard.scenarios import scenario
from energy_copilot.dashboard.evidence_builder import build_bundle
from energy_copilot.common import write_json

def event(stage,**extra):print(json.dumps(dict(dashboard_event=stage,**extra)),flush=True)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('--scenario',choices=['normal','maintenance','recovery'],required=True);p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output).resolve();allowed=(ROOT/'data/runs/dashboard_v1/live').resolve()
    if not out.is_relative_to(allowed):raise ValueError('Output outside dashboard runtime')
    if (out/'bundle.json').exists() or (out/'episode').exists():raise ValueError('Retain existing live result')
    event('integrity_check_started');protect();event('integrity_check_completed')
    from energy_copilot.supervisor import Supervisor,RuleBasedModel,EpisodeRequest
    from energy_copilot.supervisor.stack_backend import StackBackend
    s=scenario(args.scenario)
    event('preparing_matched_public_state',seed=s['seed'],day=s['day'])
    backend=StackBackend.fresh_scenario(s['seed'],s['day'],out/'execution_gateway_evaluation_only')
    class ProgressFacade:
        def call(self,tool,arguments):
            event('tool_started',tool=tool)
            result=backend.call(tool,arguments)
            event('tool_completed',tool=tool,status=getattr(result,'status',None))
            return result
    from datetime import datetime,timedelta
    at=(datetime(2026,1,5)+timedelta(days=s['day'])).isoformat()
    sup=Supervisor(ProgressFacade(),RuleBasedModel())
    packet=sup.run(EpisodeRequest(at,plan_mode='robust_maintenance' if args.scenario=='maintenance' else 'robust'),out/'episode')
    event('decision_ready',outcome=packet.outcome)
    bundle=build_bundle(args.scenario,out/'episode',out/'execution_gateway_evaluation_only',s['seed'],s['day'])
    bundle['metadata']['scope']='LIVE DETERMINISTIC SIMULATION · COMPLETED'
    write_json(out/'bundle.json',bundle);protect();event('evidence_ready',decision_id=packet.decision_id)
if __name__=='__main__':
    try:main()
    except Exception:
        event('worker_error',message='Deterministic run failed. Recommendation withheld; see private worker log.')
        import traceback;traceback.print_exc();sys.exit(1)
