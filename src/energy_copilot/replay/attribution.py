"""Paired ablations with complete-case denominators; never normalize failures away."""
import numpy as np
from .compare import paired_change


def attribution(cases):
    comparisons={}
    for name,entry in cases.items():
        if name=='S0':continue
        if entry['status']=='physically_valid' and cases['S0']['status']=='physically_valid':
            comparisons[name]=paired_change(cases['S0']['realized_metrics'],entry['realized_metrics'])
        else:comparisons[name]=dict(status='unavailable: replay infeasible or unsupported',energy_change=None,cost_change=None)
    bridge=dict(status='incomplete; do not infer combined benefit')
    if all(cases.get(n,{}).get('status')=='physically_valid' for n in ('S0','S1','S2','S3')):
        m={n:cases[n]['realized_metrics'] for n in ('S0','S1','S2','S3')}
        e=lambda n:m[n]['total_kWh'];cost=lambda n:m[n]['physical_evaluation_tariff_cost_Rs']
        bridge=dict(status='complete',label='DIGITAL-TWIN-REALIZED; SYNTHETIC-TARIFF; SYNTHETIC-PRACTICE',
            practice_only_kWh=e('S0')-e('S2'),tariff_scheduling_only_kWh=e('S0')-e('S1'),
            practice_only_cost_Rs=cost('S0')-cost('S2'),scheduling_only_cost_Rs=cost('S0')-cost('S1'),
            interaction_cost_Rs=cost('S2')+cost('S1')-cost('S0')-cost('S3'),
            combined_cost_Rs=cost('S0')-cost('S3'),combined_kWh=e('S0')-e('S3'),
            production_effect='equal output/reserve checked',maintenance_effect='none; no maintenance decision changed')
    return dict(comparisons=comparisons,bridge=bridge)


def robustness(runs):
    output={}
    for name in ('S1','S3','conservative_normal','conservative_synthetic'):
        cases=[r[name] for r in runs.values()];valid=[c for c in cases if c['status']=='physically_valid']
        paired=[paired_change(r['S0']['realized_metrics'],r[name]['realized_metrics']) for r in runs.values()
                if r['S0']['status']=='physically_valid' and r[name]['status']=='physically_valid']
        def distribution(field):
            x=[p[field] for p in paired]
            return dict(n=len(x),mean=float(np.mean(x)),median=float(np.median(x)),min=float(min(x)),max=float(max(x))) if x else dict(n=0)
        output[name]=dict(total_scenarios=len(cases),feasible=len(valid),feasible_pct=100*len(valid)/len(cases),
            lower_kWh_pct_of_all_scenarios=100*sum(p['kWh_reduction']>1e-8 for p in paired)/len(cases),
            lower_cost_pct_of_all_scenarios=100*sum(p['physical_evaluation_cost_reduction_Rs']>1e-8 for p in paired)/len(cases),
            kWh_reduction_pct_valid_pairs=distribution('kWh_reduction_pct'),cost_reduction_pct_valid_pairs=distribution('physical_evaluation_cost_reduction_pct'),
            interpretation='Improvement distributions conditional on valid pairs; all failures remain in feasibility/lower-cost denominators.')
    return output

