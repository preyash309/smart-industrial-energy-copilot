"""Trusted workflow, including a bounded failure/replan branch."""
from enum import Enum

class Stage(str,Enum):
    SNAPSHOT='SNAPSHOT'; DIAGNOSTICS='DIAGNOSTICS'; PREDICT='PREDICT'; MAINTENANCE='MAINTENANCE';
    SOLVE='SOLVE'; REPLAY='REPLAY'; CHECK='CHECK'; COMPARE='COMPARE'; FAILURE='FAILURE'; DONE='DONE'

TOOLS={Stage.SNAPSHOT:'get_public_snapshot',Stage.DIAGNOSTICS:'get_energy_diagnostics',
       Stage.PREDICT:'request_predictions',Stage.MAINTENANCE:'get_maintenance_candidates',Stage.SOLVE:'solve_robust_schedule',
       Stage.REPLAY:'replay_candidate_plan',Stage.CHECK:'check_physical_constraints',
       Stage.COMPARE:'compare_plan_to_reference',Stage.FAILURE:'get_failure_diagnostics'}


def stage_after(stage,state,request,config):
    if stage==Stage.SNAPSHOT:return Stage.DIAGNOSTICS
    if stage==Stage.DIAGNOSTICS:
        return Stage.DONE if request.mode=='MONITOR' or state['diagnostics'].no_action_needed else Stage.PREDICT
    if stage==Stage.PREDICT:return Stage.MAINTENANCE
    if stage==Stage.MAINTENANCE:return Stage.SOLVE
    if stage==Stage.SOLVE:
        if not state['plan'].optimizer_feasible:return Stage.FAILURE
        return Stage.DONE if request.mode=='PLAN' else Stage.REPLAY
    if stage==Stage.REPLAY:return Stage.CHECK if state['replay'].physically_valid else Stage.FAILURE
    if stage==Stage.CHECK:return Stage.COMPARE if state['check'].passed else Stage.FAILURE
    if stage==Stage.COMPARE:return Stage.DONE
    if stage==Stage.FAILURE:
        modes=state['failure'].permitted_replan_modes
        if modes and state['replans']<config['maximum_replan_attempts']:
            state['next_plan_mode']=modes[0];state['replans']+=1
            return Stage.SOLVE
        return Stage.DONE
    return Stage.DONE
