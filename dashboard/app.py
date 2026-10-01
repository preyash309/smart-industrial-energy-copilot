"""Launch: .venv-dashboard/Scripts/python.exe -m streamlit run dashboard/app.py"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import streamlit as st
from energy_copilot.dashboard.service import DashboardService
from energy_copilot.dashboard.scenarios import SCENARIOS,PAGES
from energy_copilot.dashboard.demo_loader import load_demo
from energy_copilot.dashboard.components import style,header,footer
from energy_copilot.dashboard.views import RENDERERS

st.set_page_config(page_title='Smart Industrial Energy Copilot',page_icon='▣',layout='wide',initial_sidebar_state='expanded')
style()
@st.cache_data(show_spinner=False)
def demo_data(key):return load_demo(key)

def reset_demo():
    for item in ('dashboard_service','service_key','operator_feedback','live_result','live_service_key'):
        st.session_state.pop(item,None)
    st.session_state['workspace_page']='Overview'
    st.session_state['scenario_selector']='normal'
    st.query_params.clear()

with st.sidebar:
    st.markdown('### ENERGY COPILOT')
    st.caption('SEE  /  PREDICT  /  ACT  /  PROVE  /  APPROVE')
    mode=st.radio('Operating mode',['DEMO','LIVE SIMULATION'],key='operating_mode')
    key=st.selectbox('Scenario',list(SCENARIOS),format_func=lambda k:SCENARIOS[k]['title'],
        index=list(SCENARIOS).index(st.query_params.get('scenario','normal')) if st.query_params.get('scenario') in SCENARIOS else 0,key='scenario_selector')
    st.caption(f"Seed {SCENARIOS[key]['seed']} · day {SCENARIOS[key]['day']} · frozen assumptions")
    page=st.radio('Workspace',PAGES,index=PAGES.index(st.query_params.get('page')) if st.query_params.get('page') in PAGES else 0,key='workspace_page')
    st.button('Reset demo',width='stretch',disabled=mode!='DEMO',on_click=reset_demo)
    st.caption('SIMULATED REFERENCE PLANT')

st.query_params['page']=page;st.query_params['scenario']=key
if st.session_state.get('service_key')!=key:
    try:
        st.session_state['dashboard_service']=DashboardService(key,bundle=demo_data(key));st.session_state['service_key']=key
    except ValueError as exc:st.error(str(exc));st.stop()

@st.fragment(run_every='1s')
def live_progress():
    job=st.session_state.get('live_job')
    if not job:return
    state=job.poll()
    with st.status('Full deterministic simulation',expanded=not state['done'],state='error' if state['error'] else 'complete' if state['done'] else 'running'):
        for event in state['events'][-6:]:
            st.write(event.get('tool',event['dashboard_event']).replace('_',' ')+' · '+('completed' if event['dashboard_event'].endswith('completed') else event.get('status') or ''))
        st.caption(f"Actual elapsed {state['elapsed']:.1f} s · no precomputed solver animation")
    if state['error']:st.error(state['error'])
    if state['done'] and state['bundle'] and st.session_state.get('live_service_key')!=str(job.output):
        st.session_state['live_result']=DashboardService(job.key,bundle=state['bundle']);st.session_state['live_service_key']=str(job.output);st.rerun()

service=st.session_state['dashboard_service']
if mode=='LIVE SIMULATION':
    st.info('LIVE SIMULATION · Actual G0 → predictions → robust optimization → replay → independent check. No real machinery control.')
    if key=='rejection':st.warning('Replay rejection is an immutable candidate excerpt. Select Adaptive recovery to run its full live episode.')
    job=st.session_state.get('live_job');running=job is not None and not job.poll()['done']
    if st.button('Run full simulation',type='primary',disabled=running or key=='rejection'):
        try:
            from energy_copilot.dashboard.live_runner import LiveJob
            st.session_state['live_job']=LiveJob(key);st.session_state.pop('live_result',None);st.session_state.pop('live_service_key',None)
        except Exception:st.error('Live worker could not start. Recommendation withheld; check the private runtime log.')
    live_progress()
    result=st.session_state.get('live_result')
    if result and result.key==key:service=result
    else:st.caption('Below: clearly labelled precomputed evidence until the live run completes. No live result is implied.')
header(service,'LIVE' if service is st.session_state.get('live_result') else 'DEMO')
try:RENDERERS[page](service)
except Exception:
    import logging
    logger=logging.getLogger('energy_copilot.dashboard.ui')
    if not logger.handlers:
        from energy_copilot.dashboard.contracts import ROOT
        log_path=ROOT/'data/runs/dashboard_v1/ui_errors.log';log_path.parent.mkdir(parents=True,exist_ok=True)
        logger.addHandler(logging.FileHandler(log_path,encoding='utf-8'))
    logger.exception('Dashboard rendering error')
    st.error('This view is unavailable. No operating action is permitted from missing or invalid evidence. See the technical log.')
footer()
