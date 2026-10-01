import html
import streamlit as st

STYLE='''
<style>
.stApp{background:#f5f7f9;color:#213841} [data-testid="stMainBlockContainer"]{padding-top:4rem;padding-bottom:2rem;max-width:1460px}
[data-testid="stSidebar"]{background:#132932} [data-testid="stSidebar"] *{color:#dce8eb}
[data-testid="stSidebar"] [data-baseweb="select"] *{color:#203740}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="combobox"]{color:#203740!important}
[data-testid="stSidebar"] [data-testid="stButton"] button *{color:#203740!important}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *{color:#aabfc8}
h1{font-size:1.85rem!important;letter-spacing:-.045rem} h2{font-size:1.25rem!important} h3{font-size:1rem!important}
[data-testid="stMetric"]{background:white;border:1px solid #e0e8eb;border-radius:9px;padding:15px 18px}
[data-testid="stMetricValue"]{font-size:1.65rem} [data-testid="stMetricLabel"]{font-size:.79rem;color:#586e78}
.brand{font-size:.75rem;letter-spacing:.12rem;font-weight:650;color:#66828d}.global{display:flex;gap:8px;flex-wrap:wrap;margin:7px 0 20px}
.badge{font-size:.70rem;letter-spacing:.025rem;padding:5px 9px;border:1px solid #d9e5e9;border-radius:5px;background:white;color:#506b75}
.badge.pass{background:#e4f2eb;color:#176a55;border-color:#b9dcca}.badge.fail{background:#fbecee;color:#ab3945;border-color:#edc4ca}
.decision{background:white;border:1px solid #dce6e9;border-left:4px solid #177e6b;border-radius:8px;padding:18px 22px;margin:10px 0}
.decision.fail{border-left-color:#bc454b}.muted{font-size:.79rem;color:#647d86}.flow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:12px 0 8px}
.asset{background:white;border:1px solid #dce6e9;border-radius:6px;padding:10px 13px;font-size:.8rem}.asset small{display:block;font-size:.62rem;color:#177e6b;margin-top:4px}
[data-testid="stDataFrame"]{width:100%} .footer{font-size:.73rem;color:#7a8b94;margin-top:24px;border-top:1px solid #e3e9ec;padding-top:12px}
</style>'''
def style():st.markdown(STYLE,unsafe_allow_html=True)
def badge(text,kind=''):
    return f'<span class="badge {html.escape(kind)}">{html.escape(text)}</span>'
def header(service,mode):
    m=service.bundle['metadata'];state='REPLAY ACCEPTED' if service.get_overview()['verified'] else 'ACTION WITHHELD'
    st.markdown('<div class="brand">SMART INDUSTRIAL ENERGY COPILOT</div>',unsafe_allow_html=True)
    st.title('SME Steel Reference Plant')
    st.markdown('<div class="global">'+badge('SIMULATED REFERENCE PLANT')+badge(mode+' MODE')+badge('Decision time '+m['origin'].replace('T',' '))+badge(m['title'])+badge(service.status,'pass' if service.status in ('VERIFIED','APPROVED') else 'fail')+badge(state)+'</div>',unsafe_allow_html=True)
def metric_cards(items):
    for offset in range(0,len(items),3):
        for col,(label,value,unit) in zip(st.columns(3),items[offset:offset+3]):
            with col:st.metric(label,value,help=unit)
def plot(fig):st.plotly_chart(fig,width='stretch',config={'displayModeBar':False})
def card(title,text,failed=False):
    st.markdown('<div class="decision'+(' fail' if failed else '')+'"><b>'+html.escape(title)+'</b><p style="margin:8px 0 0">'+html.escape(text)+'</p></div>',unsafe_allow_html=True)
def flow(eligible):
    names=[('IF','IF_01'),('Caster','CASTER'),('Billet Yard','YARD'),('RHF','RHF_01'),('Rolling Mill','MILL_01')]
    cells=[]
    for name,asset in names:
        cells.append('<div class="asset">'+name+'<small>'+('WARNING' if asset in eligible else 'NO CURRENT WARNING')+'</small></div>')
    st.markdown('<div class="flow">'+'<span style="color:#9bafb7">→</span>'.join(cells)+'</div>',unsafe_allow_html=True)
    st.caption('Supporting utilities: Cooling Pump · Compressor · AUX. Status reflects public warnings, not hidden health truth.')
def footer():st.markdown('<div class="footer">SIMULATED REFERENCE PLANT · Deterministic G0 · Human approval required · No real machinery control</div>',unsafe_allow_html=True)
