"""Host-side operator capability, never an agent tool. No real-plant executor."""
from dataclasses import dataclass
from .contracts import *


@dataclass(frozen=True)
class OperatorIdentity:
    operator_id:str
    authenticated:bool
    simulated:bool=False


class ApprovalGateway:
    def __init__(self,audit,simulated_execution_enabled=False):
        self.audit=audit;self.enabled=simulated_execution_enabled;self.__records={}

    def register(self,packet):
        self.audit.verify_chain()
        approved_evidence=[r['payload'] for r in self.audit.records if r['kind']=='final_disposition' and r['payload']['decision_id']==packet.decision_id]
        if not approved_evidence or digest(approved_evidence[-1])!=digest(packet.to_dict()):raise BoundaryError('Decision lacks trusted episode receipt')
        if packet.decision_id in self.__records:raise BoundaryError('Decision already registered')
        if packet.outcome not in ('VERIFIED_RECOMMENDATION','VERIFIED_ANALYSIS') or packet.disposition!='VERIFIED':raise BoundaryError('Unverified plan')
        if not(packet.optimizer_plan.optimizer_feasible and packet.replay_outcome.physically_valid and packet.independent_check.passed):raise BoundaryError('Missing verification gate')
        if not(packet.optimizer_plan.schedule_id==packet.replay_outcome.schedule_id==packet.independent_check.schedule_id and
               packet.replay_outcome.replay_id==packet.independent_check.replay_id):raise BoundaryError('Verification identity mismatch')
        self.__records[packet.decision_id]=(packet,'VERIFIED',digest(packet.to_dict()))

    def feedback(self,feedback,operator):
        feedback.validate()
        if type(operator) is not OperatorIdentity or operator.authenticated is not True or not operator.operator_id:
            raise BoundaryError('Authenticated host-side operator required')
        packet,status,h=self.__records[feedback.decision_id]
        if status in ('REJECTED','EXECUTED','APPROVED'):raise BoundaryError('Terminal operator decision is immutable')
        if digest(packet.to_dict())!=h:raise BoundaryError('Decision altered')
        new='APPROVED' if feedback.action=='approve' else 'REJECTED' if feedback.action=='reject' else status
        self.__records[feedback.decision_id]=(packet,new,h)
        self.audit.append('operator_feedback',dict(feedback=primitive(feedback),operator_id=operator.operator_id,
            explicit_simulated_approval=operator.simulated,previous_disposition=status,disposition=new,packet_sha256=h))
        return new

    def execute_simulation(self,decision_id,executor):
        packet,status,h=self.__records[decision_id]
        if not self.enabled or status!='APPROVED':raise BoundaryError('Explicit approval and enabled simulation gateway required')
        if digest(packet.to_dict())!=h:raise BoundaryError('Approved decision altered')
        receipt=executor(packet.optimizer_plan.schedule_id)
        if type(receipt) is not dict or receipt.get('schedule_id')!=packet.optimizer_plan.schedule_id or receipt.get('status')!='EXECUTED':
            raise BoundaryError('Invalid simulation acknowledgement')
        self.__records[decision_id]=(packet,'EXECUTED',h)
        self.audit.append('simulated_execution',dict(receipt=receipt,decision_id=decision_id,disposition='EXECUTED'))
        return receipt

    def status(self,decision_id):return self.__records[decision_id][1]
