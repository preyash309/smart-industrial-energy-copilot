from energy_copilot.dashboard.contracts import protect
from energy_copilot.dashboard.evidence_builder import build_demo
if __name__=='__main__':
    n=protect();build_demo();assert protect()==n;print('Four demo scenarios frozen; protected files unchanged:',n)
