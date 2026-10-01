"""Supervisory integration demos. No real execution or automatic human approval."""
from pathlib import Path
import argparse,json
from energy_copilot.common import write_json,sha256
from energy_copilot.supervisor import Supervisor,RuleBasedModel,EpisodeRequest
from energy_copilot.supervisor.stack_backend import StackBackend
from energy_copilot.supervisor.policy import guard,configuration
from energy_copilot.supervisor.contracts import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=['normal','maintenance','late_day'],required=True)
    p.add_argument('--attempt',default='initial')
    p.add_argument('--emulate-approval',action='store_true',help='Explicit offline host approval; simulated execution only')
    a=p.parse_args()
    if not a.attempt.replace('_','').isalnum():raise ValueError('Invalid attempt name')
    if Path('supervision/supervisor_v1/release_manifest.json').exists():raise RuntimeError('Supervisor evidence frozen')
    declared={'normal':(3001,7,'robust'),'maintenance':(3002,14,'robust_maintenance'),'late_day':(3003,28,'robust')}
    seed,day,mode=declared[a.case];out=Path('supervision/supervisor_v1/integration')/(a.case if a.attempt=='initial' else a.case+'_'+a.attempt)
    if out.exists():raise RuntimeError('Retain existing integration attempt; use an explicit successor for a new design')
    guard();backend=StackBackend.fresh_scenario(seed,day,out/'execution_gateway_evaluation_only')
    from datetime import datetime,timedelta
    at=(datetime(2026,1,5)+timedelta(days=day)).isoformat()
    supervisor=Supervisor(backend,RuleBasedModel());packet=supervisor.run(EpisodeRequest(at,plan_mode=mode),out/'episode')
    if a.emulate_approval and packet.outcome=='VERIFIED_RECOMMENDATION':
        from energy_copilot.supervisor.approval import ApprovalGateway,OperatorIdentity
        from energy_copilot.supervisor.contracts import OperatorFeedback
        gateway=ApprovalGateway(supervisor.last_audit,simulated_execution_enabled=True)
        gateway.register(packet)
        gateway.feedback(OperatorFeedback(packet.decision_id,'approve','offline_explicit_simulated_approval'),
            OperatorIdentity('offline-simulation-operator',True,simulated=True))
        gateway.execute_simulation(packet.decision_id,backend.execute_approved_simulation)
        supervisor.last_audit.verify_chain()
    write_json(out/'integration_result.json',dict(case=a.case,seed=seed,day=day,scope='LIVE_FROZEN_DETERMINISTIC_STACK',
        outcome=packet.outcome,decision_id=packet.decision_id,metrics=supervisor.last_audit.metrics,
        assumptions='Frozen E4, Phase-F policy, synthetic practice and tariff; no LLM inference and no policy selection.',
        source_hashes=dict(phase_F_release=sha256('replay/maintenance_v1/release_manifest.json'),supervisor_config=sha256('configs/supervisor_v1.yaml'),
            supervisor_source=sha256('src/energy_copilot/supervisor/supervisor.py'),gateway=sha256('src/energy_copilot/supervisor/stack_backend.py'))))
    guard();print(a.case,packet.outcome,supervisor.last_audit.metrics,flush=True)


if __name__=='__main__':main()
