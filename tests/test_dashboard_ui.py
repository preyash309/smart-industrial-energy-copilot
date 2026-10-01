"""Isolated Streamlit tests; no modification of the frozen backend environment."""
import pytest
pytest.importorskip('streamlit');pytest.importorskip('plotly')
from streamlit.testing.v1 import AppTest
from energy_copilot.dashboard.contracts import ROOT
from energy_copilot.dashboard.scenarios import PAGES,SCENARIOS

@pytest.mark.parametrize('scenario',list(SCENARIOS))
def test_seven_screens(scenario):
    app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    app.selectbox(key='scenario_selector').select(scenario).run()
    for page in PAGES:
        app.radio(key='workspace_page').set_value(page).run()
        assert not app.exception,[x.message for x in app.exception]
        assert not any('This view is unavailable' in x.value for x in app.error)
        assert any('SIMULATED REFERENCE PLANT' in x.value for x in app.markdown)

def test_confirmation_and_failed_approval():
    app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    app.radio(key='workspace_page').set_value('Decision Center').run()
    next(b for b in app.button if b.label=='Approve').click().run()
    assert app.session_state['dashboard_service'].status=='VERIFIED'
    assert any('confirmation' in x.value.lower() for x in app.error)
    app.checkbox[0].check().run();next(b for b in app.button if b.label=='Approve').click().run()
    assert app.session_state['dashboard_service'].status=='APPROVED'
    app.selectbox(key='scenario_selector').select('rejection').run()
    assert next(b for b in app.button if b.label=='Approve').disabled

def test_reset_session():
    app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    original=app.session_state['dashboard_service'].session_id
    next(b for b in app.button if b.label=='Reset demo').click().run()
    assert app.session_state['dashboard_service'].session_id!=original
    assert app.session_state['dashboard_service'].status=='VERIFIED'

def test_live_only_on_explicit_request():
    app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    app.radio(key='operating_mode').set_value('LIVE SIMULATION').run()
    assert 'live_job' not in app.session_state
    assert any(b.label=='Run full simulation' for b in app.button)
    assert not app.exception

def test_reset_restores_scenario_and_page():
    app=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=30).run()
    app.selectbox(key='scenario_selector').select('rejection').run()
    app.radio(key='workspace_page').set_value('Decision Center').run()
    next(b for b in app.button if b.label=='Reset demo').click().run()
    assert app.selectbox(key='scenario_selector').value=='normal'
    assert app.radio(key='workspace_page').value=='Overview'
    assert app.session_state['dashboard_service'].key=='normal'

def test_compact_tariff_shading_preserves_every_slot():
    from energy_copilot.dashboard.service import DashboardService
    from energy_copilot.dashboard.charts import schedule
    s=DashboardService();rows=s.get_schedule_comparison()
    fig=schedule(rows['heats'],s.packet['timestamp'],rows['load'])
    colours={'offpeak':'rgba(23,126,107,.08)','normal':'rgba(112,130,142,.06)','peak':'rgba(185,121,24,.12)'}
    assert len(fig.layout.shapes)<len(rows['load'])
    for r in rows['load']:
        middle=(r['slot']+.5)*15
        covering=[shape for shape in fig.layout.shapes if shape.x0<=middle<shape.x1]
        assert len(covering)==1 and covering[0].fillcolor==colours[r['tariff_period']]
