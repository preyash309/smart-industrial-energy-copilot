"""Evaluation-only matched physical trace; never used by the planner."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    base=Path('replay/maintenance_v1/development/seed_2001_day_14')
    origin=pd.Timestamp('2026-01-19T00:00:00');end=origin+pd.Timedelta(hours=12)
    data={}
    for strategy in ('F0','F2'):
        folder=base/strategy
        truth=pd.read_parquet(folder/'simulation'/'latent_truth.parquet')
        truth=truth[truth.timestamp.ge(origin)&truth.timestamp.lt(end)]
        event=pd.read_parquet(folder/'simulation'/'events.parquet')
        risk=pd.read_parquet(folder/'health_prediction_history.parquet')
        data[strategy]=dict(truth=truth,event=event,risk=risk)
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True,layout='constrained')
    colors={'F0':'#9c2f43','F2':'#126e76'}
    for strategy,d in data.items():
        t=d['truth'];style='--' if strategy=='F0' else '-';color=colors[strategy]
        for ax,asset,field,scale in ((axes[0],'IF_01','kW',1000),(axes[1],'PMP_01','kW',1),
                                     (axes[2],'MAIN','yard_stock_t',1)):
            rows=t[t.asset_id.eq(asset)].sort_values('timestamp')
            ax.step(rows.timestamp,rows[field]/scale,where='post',label=strategy,color=color,linestyle=style,linewidth=1.4)
        p=d['risk'];p=p[p.asset_id.eq('PMP_01')].copy()
        p=p[pd.to_datetime(p.decision_time,format='mixed').between(origin,end)]
        axes[3].plot(pd.to_datetime(p.decision_time,format='mixed'),p.calibrated_probability,
                     marker='o',markersize=2.7,label=strategy,color=color,linestyle=style)
    for strategy,d in data.items():
        ev=d['event'];ev=ev[ev.asset_id.eq('PMP_01')&ev.type.isin(('failure','preventive_service'))]
        for row in ev.itertuples():
            if row.end<origin or row.start>end:continue
            for ax in axes:
                ax.axvspan(max(row.start,origin),min(row.end,end),color=colors[strategy],alpha=.14)
    axes[3].axhline(.55,color='#444',linestyle=':',linewidth=1,label='policy eligibility')
    for ax,label in zip(axes,('IF power (MW)','Cooling pump (kW)','Billet yard (t)','Public pump risk, P(failure in 24 h)')):
        ax.set_ylabel(label);ax.grid(alpha=.2)
    axes[3].set_ylim(-.05,1.05);axes[3].set_xlabel('2026-01-19 local time')
    axes[0].legend(ncol=2,loc='upper right');axes[3].legend(ncol=3,loc='upper right')
    fig.suptitle('Matched synthetic replay: F0 pump failure versus F2 preventive service (development seed 2001)')
    out=Path('reports/figures/phase2f_matched_pump_trace.png');out.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(out,dpi=160);plt.close(fig)
    print(out)


if __name__=='__main__':main()
