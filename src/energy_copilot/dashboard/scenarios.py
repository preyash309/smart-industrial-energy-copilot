SCENARIOS={
 'normal':dict(title='Normal optimization',case='late_day',attempt='late_day_release_approval',seed=3003,day=28,
     story='A robust schedule passes replay and independently checked constraints.'),
 'maintenance':dict(title='Maintenance warning',case='maintenance',attempt='maintenance_release_checks',seed=3002,day=14,
     story='Elevated pump risk makes service eligible. A rejected continuation is withheld.'),
 'rejection':dict(title='Replay rejection',case='normal',attempt='normal_release_checks',seed=3001,day=7,
     story='The first forecast-feasible candidate fails physical replay. This excerpt remains unapproved.'),
 'recovery':dict(title='Adaptive recovery',case='normal',attempt='normal_release_checks',seed=3001,day=7,
     story='The first candidate fails; bounded deterministic replanning produces an accepted replacement.')}
PAGES=('Overview','Energy','Optimise','Maintenance','Decision Center','Impact','Evidence / Audit')

def scenario(key):
    from .contracts import DashboardError
    if key not in SCENARIOS:raise DashboardError('Unknown curated scenario.')
    return SCENARIOS[key]
