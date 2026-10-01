"""Read a frozen checked demo packet; no optimization or replay is implied."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from energy_copilot.dashboard.service import DashboardService
service=DashboardService('normal')
packet=service.get_decision_packet()
print(json.dumps({"scope":"PRECOMPUTED VERIFIED DEMO","decision_id":packet['decision_id'],
    "outcome":packet['outcome'],"operator_status":service.status,
    "predicted":packet['optimizer_plan'],"replay":packet['replay_outcome'],
    "required_action":packet['required_human_action']},indent=2))
