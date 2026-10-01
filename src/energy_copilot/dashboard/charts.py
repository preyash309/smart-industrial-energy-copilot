"""Presentation only; receives facade-projected rows, no optimizer or truth access."""
import plotly.graph_objects as go
from datetime import datetime

GREEN='#177e6b';BLUE='#3675a9';AMBER='#b97918';RED='#bc454b';GREY='#70828e'
def theme(fig,height=300):
    fig.update_layout(height=height,font=dict(family='Arial, sans-serif',size=12,color='#344750'),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=12,r=12,t=22,b=20),
        legend=dict(orientation='h',y=1.13,x=0),hovermode='x unified')
    fig.update_xaxes(showgrid=False,zeroline=False);fig.update_yaxes(gridcolor='#edf1f3',zeroline=False)
    return fig

def load(rows):
    points=[r for r in rows if r['asset_id']=='MAIN']
    fig=go.Figure(go.Scatter(x=[r['timestamp'] for r in points],y=[r.get('kW') for r in points],
        name='MAIN measured',mode='lines',line=dict(color=GREEN,width=2.5),fill='tozeroy',fillcolor='rgba(23,126,107,.07)',connectgaps=False))
    fig.update_yaxes(title_text='Electrical demand (kW)');fig.update_xaxes(title_text='Local interval start')
    return theme(fig)

def assets(rows):
    points=[r for r in rows if r['asset_id']!='MAIN'];fig=go.Figure(go.Bar(x=[r.get('kWh') for r in points],y=[r['asset_id'] for r in points],
        orientation='h',marker_color=GREEN,hovertemplate='%{y}: %{x:,.1f} kWh<extra></extra>'))
    fig.update_xaxes(title_text='QC public feeder electricity (kWh)');return theme(fig,280)

def expected_actual(heats):
    fig=go.Figure()
    for field,name,color in [('expected_kWh','Historical expected',BLUE),('kWh','Actual completed heat',GREEN)]:
        fig.add_bar(x=[r['heat_id'].split('_')[-1] for r in heats],y=[r.get(field) for r in heats],name=name,marker_color=color)
    fig.update_layout(barmode='group');fig.update_yaxes(title_text='Heat electricity (kWh)');fig.update_xaxes(title_text='Heat')
    return theme(fig)

def background(predictions):
    fig=go.Figure()
    for field,name,color in [('aux_p50_kW','AUX p50',GREEN),('aux_p90_kW','AUX p90',AMBER)]:
        values=predictions[field]
        fig.add_trace(go.Scatter(x=[i/4 for i in range(len(values))],y=values,mode='lines',name=name,line_color=color))
    fig.update_xaxes(title_text='Hours after forecast origin')
    fig.update_yaxes(title_text='Predicted background demand (kW)')
    return theme(fig,240)

def sec_distribution(heats):
    fig=go.Figure(go.Histogram(x=[r['SEC_kWh_per_t'] for r in heats],marker_color=GREEN,nbinsx=12))
    fig.update_xaxes(title_text='SEC (kWh/t liquid)');fig.update_yaxes(title_text='Completed heats');return theme(fig,250)

def schedule(rows,origin,tariffs,maintenance=(),reference=False):
    fig=go.Figure();base=datetime.fromisoformat(origin)
    def minutes(at):return (datetime.fromisoformat(at)-base).total_seconds()/60
    if reference:
        for row in rows:
            a=datetime.fromisoformat(row['start_time']);b=datetime.fromisoformat(row['end_time'])
            start=a.hour*60+a.minute+a.second/60;duration=(b-a).total_seconds()/60
            fig.add_trace(go.Bar(x=[duration],base=[start],y=['IF'],orientation='h',marker_color=GREY,
                name=row['heat_id'],showlegend=False,hovertemplate=row['heat_id']+' · prior-day observed<extra></extra>'))
    else:
        for row in rows:
            start=minutes(row['start']);duration=minutes(row['predicted_end'])-start
            fig.add_trace(go.Bar(x=[duration],base=[start],y=['IF'],orientation='h',marker_color=GREEN,
                name=row['heat_id'],showlegend=False,hovertemplate=row['heat_id']+' · predicted duration<extra></extra>'))
    # Merge contiguous bands for display only. Repeated add_vrect calls rescan
    # every heat trace and made a 96-slot static figure unnecessarily slow.
    bands=[]
    for period in tariffs:
        color={'offpeak':'rgba(23,126,107,.08)','normal':'rgba(112,130,142,.06)','peak':'rgba(185,121,24,.12)'}.get(period.get('tariff_period'),'rgba(112,130,142,.06)')
        left,right=minutes(period['interval_start']),minutes(period['interval_end'])
        if bands and bands[-1]['fillcolor']==color and bands[-1]['x1']==left:
            bands[-1]['x1']=right
        else:bands.append(dict(type='rect',xref='x',yref='paper',x0=left,x1=right,y0=0,y1=1,fillcolor=color,line=dict(width=0),layer='below'))
    fig.update_layout(shapes=bands)
    for window in maintenance:
        start=minutes(window['start_time']);fig.add_trace(go.Bar(x=[window['duration_min']],base=[start],y=[window['asset_id']+' service'],
            orientation='h',marker_color=AMBER,name='Preventive candidate',showlegend=False))
    fig.update_layout(barmode='overlay',bargap=.38)
    fig.update_xaxes(range=[0,1440],tickvals=list(range(0,1441,180)),ticktext=[f'{n//60:02d}:00' for n in range(0,1441,180)],title_text='Local time of day')
    return theme(fig,170 if not maintenance else 230)

def rolling_and_inventory(trajectory):
    fig=go.Figure();fig.add_trace(go.Bar(x=[r['interval_start'] for r in trajectory],y=[r['rolling_billet_t'] for r in trajectory],
        marker_color=BLUE,name='Predicted rolling feed (t/slot)'))
    fig.update_yaxes(title_text='Rolling billet feed (t / 15 min)');return theme(fig,220)

def health(rows,asset):
    r=[x for x in rows if x['asset_id']==asset and x.get('vibration_mm_s') is not None]
    fig=go.Figure(go.Scatter(x=[x['timestamp'] for x in r],y=[x['vibration_mm_s'] for x in r],mode='lines',line_color=BLUE,name=asset))
    fig.update_yaxes(title_text='Observed vibration (mm/s)');fig.update_xaxes(title_text='Posted local interval');return theme(fig,220)

def inventory(rows):
    fig=go.Figure(go.Scatter(x=[r['timestamp'] for r in rows],y=[r['inventory_t'] for r in rows],mode='lines',line_color=GREEN,name='Predicted inventory'))
    fig.add_hline(y=200,line_dash='dot',line_color=GREY,annotation_text='200 t limit')
    fig.update_yaxes(title_text='Billet inventory (t)',range=[0,210]);return theme(fig,220)
