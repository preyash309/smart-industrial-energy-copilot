"""UI facade. Demo never imports/calls the optimizer, simulator or live runner."""
from pathlib import Path
from dataclasses import dataclass
import copy,json,uuid
from .contracts import ROOT,read_json,validate_bundle,typed,DashboardError,file_hash
from .demo_loader import load_demo

class DashboardService:
    def __init__(self,key='normal',bundle=None,runtime_root=None):
        self.bundle=validate_bundle(copy.deepcopy(bundle)) if bundle else load_demo(key)
        self.key=self.bundle['metadata']['scenario'];self.packet=self.bundle['packet']
        self.session_id=uuid.uuid4().hex;self._directory=Path(runtime_root or ROOT/'data/runs/dashboard_v1/operator_sessions')/self.session_id
        self._approval=None;self._audit=None;self._status=self.packet['disposition'];self.last_feedback=None

    def get_overview(self):
        p=self.packet;real=p.get('replay_outcome');plan=p['optimizer_plan'];summary=self.bundle.get('public_summary')
        verified=p['outcome']=='VERIFIED_RECOMMENDATION'
        return dict(metadata=self.bundle['metadata'],status=self.status,verified=verified,
            production_t=summary['bars_t'] if summary else plan['production_target_t'],
            production_label='Verified production' if summary else 'Production target',
            electricity_kWh=real['realized_energy_kWh'] if verified else plan['predicted_energy_kWh'],
            SEC=summary['IF_SEC'] if summary else plan['predicted_SEC'],
            peak_kVA=real['realized_peak_kVA'] if verified else plan['predicted_peak_kVA'],
            cost_Rs=real['realized_cost_Rs'] if verified else plan['predicted_cost_Rs'],
            label='DIGITAL-TWIN-REALIZED' if verified else 'OPTIMIZER-PREDICTED · UNVERIFIED',
            alert_count=len(self.bundle['diagnostics'])+len(self.bundle['metadata']['maintenance_eligible_assets']),
            snapshot=p['snapshot'],predictions=p['predictions'])

    def get_energy_view(self):return {k:copy.deepcopy(self.bundle[k]) for k in ('replay_observations','observed_history','heat_analytics','asset_energy','diagnostics')}
    def get_schedule_comparison(self):
        result=copy.deepcopy(self.bundle['schedule'])
        result.update(reference_schedule=result['prior_observed_heats'],predicted_schedule=result['heats'],predicted_trajectory=result['load'])
        return result
    def get_maintenance_view(self):
        return dict(health=copy.deepcopy(self.packet['predictions']['health_risk']),
            eligibility=self.bundle['metadata']['maintenance_eligible_assets'],selected=self.packet['optimizer_plan']['maintenance_actions'],
            initial_selected=self.packet['alternatives_considered'][0]['maintenance_actions'],observations=self.packet['snapshot']['observations'],
            history=self.bundle['observed_history'],verified=self.packet['outcome']=='VERIFIED_RECOMMENDATION')
    def get_decision_packet(self):return copy.deepcopy(self.packet)
    def get_impact_summary(self):
        root=ROOT/'dashboard/evidence_v1';manifest=read_json(root/'manifest.json')
        if file_hash(root/'impact.json')!=manifest['files']['impact.json']:raise DashboardError('Impact evidence integrity check failed.')
        return read_json(root/'impact.json')
    def get_evidence(self):return dict(metadata=self.bundle['metadata'],packet=self.get_decision_packet(),approval_status=self.status,session_id=self.session_id)
    @property
    def status(self):return self._approval.status(self.packet['decision_id']) if self._approval else self._status

    def _gateway(self):
        if self._audit:return
        from energy_copilot.supervisor.audit import AuditLog
        from energy_copilot.supervisor.approval import ApprovalGateway
        from energy_copilot.supervisor.contracts import DecisionPacket
        source=ROOT/self.bundle['metadata']['source_episode']/'audit.jsonl'
        rows=[json.loads(x) for x in source.read_text().splitlines()]
        terminal=next(i for i,x in enumerate(rows) if x['kind']=='final_disposition')
        audit=AuditLog(self._directory);audit.records=rows[:terminal+1]
        (self._directory/'audit.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in audit.records),encoding='utf-8')
        audit.verify_chain();audit.append('dashboard_session',dict(session_id=self.session_id,scenario=self.key,
            mode='LIVE-OPERATOR-REVIEW' if self.bundle['metadata']['scope'].startswith('LIVE') else 'DEMO-OPERATOR-REVIEW',
            source_audit_sha256=file_hash(source),explicit_simulated_operator=True,original_approval_is_not_inherited=True))
        self._audit=audit
        if self.packet['outcome']=='VERIFIED_RECOMMENDATION':
            packet=typed(DecisionPacket,self.packet)
            self._approval=ApprovalGateway(audit,simulated_execution_enabled=False);self._approval.register(packet)

    def feedback(self,action,confirmed=False,reason=None):
        if action not in ('approve','reject','defer'):raise DashboardError('Unsupported operator action.')
        if action=='approve' and not confirmed:raise DashboardError('Explicit operator confirmation required.')
        if action=='approve' and self.packet['outcome']!='VERIFIED_RECOMMENDATION':raise DashboardError('No verified recommendation available for approval.')
        if self.status in ('APPROVED','REJECTED','EXECUTED'):raise DashboardError('Terminal operator decision is immutable. Reset starts a new review session.')
        self._gateway()
        from energy_copilot.supervisor.contracts import OperatorFeedback
        from energy_copilot.supervisor.approval import OperatorIdentity
        fb=OperatorFeedback(self.packet['decision_id'],action,'dashboard_operator_review',reason)
        if self._approval:
            self._approval.feedback(fb,OperatorIdentity('prototype-operator',True,simulated=True))
        else:
            fb.validate();self._status='REJECTED' if action=='reject' else self._status
            self._audit.append('unverified_operator_review',dict(decision_id=self.packet['decision_id'],action=action,disposition=self._status,
                reason=reason,explicit_simulated_operator=True,execution_permitted=False))
        self.last_feedback=action;self._audit.verify_chain()
        return self.status

    def approve_decision(self,confirmed=False,reason=None):return self.feedback('approve',confirmed,reason)
    def reject_decision(self,reason=None):return self.feedback('reject',reason=reason)
    def defer_decision(self,reason=None):return self.feedback('defer',reason=reason)
