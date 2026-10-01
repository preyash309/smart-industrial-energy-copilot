"""Freeze new dashboard evidence only after regression, UI and live gates pass."""
import json,re,sys
from pathlib import Path
from energy_copilot.dashboard.contracts import ROOT,read_json,file_hash,protect
from energy_copilot.dashboard.demo_loader import load_demo
from energy_copilot.dashboard.scenarios import SCENARIOS,PAGES

RELEASE=ROOT/'dashboard/release_v1/manifest.json'
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def log_result(name):
    raw=(ROOT/'data/tmp'/name).read_bytes()
    text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
    passed=re.findall(r'(\d+) passed',text)
    if not passed or re.search(r'\d+ failed|FAILURES|ERRORS',text):raise RuntimeError('Test gate incomplete: '+name)
    return dict(passed=int(passed[-1]),skipped=int(re.findall(r'(\d+) skipped',text)[-1]) if ' skipped' in text else 0,
                source='data/tmp/'+name,sha256=file_hash(ROOT/'data/tmp'/name))
def md(name,text):
    (ROOT/'reports'/name).write_text(text.strip()+'\n',encoding='utf-8')
def verify():
    count=protect();release=read_json(RELEASE)
    bad=[p for p,h in release['files'].items() if not (ROOT/p).is_file() or file_hash(ROOT/p)!=h]
    if bad:raise RuntimeError('Dashboard release changed: '+str(bad[:5]))
    print('PHASE III-A RELEASE VERIFIED',len(release['files']),'dashboard files;',count,'upstream files unchanged')
def main():
    if '--verify' in sys.argv:verify();return
    if RELEASE.exists():raise RuntimeError('Dashboard v1 already frozen. Use a successor version.')
    protected=protect()
    full=log_result('phase3a_regression_release.log');ui=log_result('phase3a_ui_release.log')
    if full['passed']<492 or ui['passed']<40:raise RuntimeError('Incomplete regression/UI matrix')
    browser=read_json(ROOT/'reports/screenshots/phase3a/ui_audit.json')
    if len(browser)!=18 or any(r['horizontal_overflow'] or r['render_error'] or r['page_errors'] for r in browser):
        raise RuntimeError('Real-browser responsive gate failed')
    navigation=read_json(ROOT/'reports/screenshots/phase3a/navigation_audit.json')
    flow=read_json(ROOT/'reports/screenshots/phase3a/interaction_audit.json')
    for key in ('confirmation_enforced','approval_audited','reset_isolated','rejected_approval_disabled','demo_before_live_explicit','live_backend_executed'):
        if flow[key] is not True:raise RuntimeError('Interactive workflow gate failed: '+key)
    live_root=ROOT/flow['live_output'];live=read_json(live_root/'bundle.json')
    if live['packet']['outcome']!='VERIFIED_RECOMMENDATION' or not live['packet']['independent_check']['passed']:
        raise RuntimeError('Actual live backend gate failed')
    bundles={key:load_demo(key) for key in SCENARIOS}
    deck=read_json(ROOT/'dashboard_deck_metrics.json')
    for row in deck['metrics']:
        source=ROOT/row['source_artifact'];value=read_json(source)
        if file_hash(source)!=row['source_sha256']:raise RuntimeError('Historical evidence changed')
        for part in row['source_field'].split('.'):value=value[part]
        if value!=row['value']:raise RuntimeError('Deck metric is not the exact released field')
    summary=dict(status='PHASE III-A COMPLETE',backend='frozen deterministic G0',live_G1='PENDING / OUT OF SCOPE',
        pages=list(PAGES),scenarios=[dict(key=k,title=SCENARIOS[k]['title'],seed=b['metadata']['seed'],day=b['metadata']['day'],
            outcome=b['packet']['outcome'],scope=b['metadata']['scope'],source_episode=b['metadata']['source_episode']) for k,b in bundles.items()],
        full_regression=full,isolated_dashboard_tests=ui,protected_upstream_files=protected,upstream_hash_status='PASS',
        browser=dict(views=len(browser),viewports=[1440,1280],overflow=0,render_errors=0),navigation=navigation,
        live_interaction=flow,deck_metric_count=len(deck['metrics']),human_approval='EXPLICIT, AUDITED; EXECUTION DISABLED')
    write(ROOT/'reports/phase3a_validation.json',summary)
    scenario_rows='\n'.join(f"| {SCENARIOS[k]['title']} | {b['metadata']['seed']} / {b['metadata']['day']} | {b['packet']['outcome']} | {b['metadata']['scope']} |" for k,b in bundles.items())
    md('phase3a_summary.md',f'''# Phase III-A dashboard release
**PHASE III-A COMPLETE.** Seven operator pages consume four coherent frozen demo bundles. An explicit live run also reached VERIFIED_RECOMMENDATION through unchanged G0, PredictionService, robust optimization, matched replay and the independent checker. Live G1 remains pending and is not part of this release.

Launch from `D:\\Projects\\Schneider Electric`:
```powershell
.venv-dashboard\\Scripts\\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```
Open http://127.0.0.1:8501. Setup/locked dependencies and screenshot commands are in `docs/phase3a_usage.md`. Streamlit 1.64.0, Plotly 7.1.0 and PyYAML 6.0.3 run in the isolated UI environment; the original `.venv` runs all physical backend work.

Pages: Overview; Energy; Optimise; Maintenance; Decision Center; Impact; Evidence / Audit. The thin DashboardService supplies public/QC analytics, prediction summaries, optimizer schedules, replay evidence and approval operations. Page modules contain presentation, not plant decisions. The Energy forecast expander displays heat p50/p90 energy/duration and AUX-only forecasts; completed heat diagnostics are kept separate.

| Demo scenario | Seed / day | Supervisory outcome | Scope |
|---|---|---|---|
{scenario_rows}

Normal and adaptive cases are physically verified; the pump-maintenance candidate and retained initial duration-rejected candidate remain visible and cannot be approved. The rejection excerpt is not a new canonical supervisor decision. Missing failed-case traces stay unavailable. All pages share one selected bundle. The reference timeline is the preceding observed day from that run, not the matched tariff-cost counterfactual.

Demo evidence is precomputed and labelled. Only immutable evidence is cached. Live jobs and approvals are session-local. The real browser live test took {flow['live_elapsed_ms']/1000:.3f} s, including public-state construction, optimization, replay, evidence projection and protected-file checks. Actual backend tool start/completion events drive progress. The normal live output is `{flow['live_output']}`; the other curated live scenarios use the same adapter but were not rerun through the UI for this release. Arbitrary seed entry is not supported by the frozen integration facade.

VERIFIED is not APPROVED. Explicit prototype-operator confirmation appends a hash-chained fork of the canonical audit; historical approval is not inherited. Approve/reject/defer and reset are tested. Rejection is immutable; reset starts a new review while preserving earlier logs. Unverified plans cannot be approved. Both simulated execution and real machinery execution are disabled in this UI. These are explicit simulated operator actions, not authenticated production identities.

Responsive real-browser audit: {len(browser)} views at 1440×900 and 1280×900, zero horizontal-overflow/render/page-error findings. Screenshots in `reports/screenshots/phase3a` include the seven pages, rejection, adaptive recovery, explicit approval and a real live result. Warm navigation across 14 transitions averaged {navigation['mean_navigation_ms']/1000:.3f} s, maximum {navigation['max_navigation_ms']/1000:.3f} s on this machine. Cold-tab loading is separately recorded and is slower. Contiguous tariff shading fixed the initial approximately nine-second chart-build bottleneck without changing slot values.

Full command: `$env:PYTHONPATH='src;.'; .venv\\Scripts\\python.exe -m pytest -q`: **{full['passed']} passed, {full['skipped']} skipped**. The skipped module requires UI packages, intentionally absent from the frozen environment. Isolated command: `.venv-dashboard\\Scripts\\python.exe -m pytest tests/test_dashboard.py tests/test_dashboard_ui.py -q`: **{ui['passed']} passed**. Includes all four scenarios × seven screens, schema/time/boundary checks, numerical/evidence separation, approval/reset/session isolation and chart shading preservation. Browser flow additionally exercises the live button and actual backend.

All **{protected:,} protected upstream files are unchanged**. New code/artifacts only: `src/energy_copilot/dashboard/`, `dashboard/`, `.streamlit/config.toml`, `configs/dashboard_v1.yaml`, `configs/phase3a_readonly_manifest.json`, `requirements-dashboard*.txt`, `scripts/phase3a*`, `scripts/setup_dashboard.ps1`, `tests/test_dashboard*.py`, `docs/phase3a_usage.md`, `reports/phase3a*`, screenshots, deck metrics and new dashboard runtime outputs. Exact paths/hashes are in `dashboard/release_v1/manifest.json`.

`dashboard_deck_metrics.json` contains {len(deck['metrics'])} exact released fields with source path/field/hash, unit, evidence label, population and caveat. Phase D's 2.44% electricity and 4.21% synthetic tariff reductions remain distinct matched simulated effects; E's 0/10 versus 10/10 is held-out replay evidence; F's 16 services/14 avoided failures/2 undetermined and 91.67% F0 versus 87.50% F2 feasibility are shown honestly. No field savings, industrial maintenance ROI or external-benchmark-to-plant transfer is claimed.

Remaining limits: synthetic practice/tariff/maintenance, reduced-order plant physics, snapshot-based demonstrations, missing failed-case meter traces, fixed curated live cases, unauthenticated prototype operator identity and single-host session workers. Live LLM qualification, real authentication, ingestion, PLC control, cloud deployment, tariff billing and maintenance ROI are outside scope. The local dashboard should not be exposed publicly as a production service.

Three-minute path: Overview → Energy → Optimise → Replay rejection → Adaptive recovery / approval → Maintenance → Impact → Evidence. Use labelled Demo Mode; optional live appendix is separate. Full cues are in `reports/phase3a_demo_script.md`.

Ready for **Phase III-B — Live Copilot Integration + Final Submission Packaging** as a deterministic, screenshot-ready prototype. Live G1 must still be independently qualified; this readiness statement does not certify an LLM or industrial deployment.
''')
    md('phase3a_ui_audit.md',f'''# Phase III-A UI and evidence audit
PASS: seven pages × four scenarios in AppTest; 18 real Edge browser views at two laptop widths; charts/tables fully hydrated before capture; chart units and evidence labels visually inspected; strong rejection/approval states. No horizontal overflow, uncaught browser errors, placeholder prose or unsupported savings claims found in the selected screenshots.

PASS: explicit confirmation before approval; separate VERIFIED/APPROVED; failed candidate approval disabled; audit forks preserve source evidence and previous review; reset restores Normal/Overview and fresh review; LIVE displays DEMO evidence explicitly until its own result is complete.

PASS: actual LiveJob launched by browser button; frozen prediction/solver/replay/check tool events in worker log; result VERIFIED_RECOMMENDATION, independent check passed. Only normal live scenario was browser-executed; rejected and adaptive outcomes in Demo use real frozen Phase-G integration evidence.

Warm navigation: mean {navigation['mean_navigation_ms']:.1f} ms; max {navigation['max_navigation_ms']} ms over 14 transitions. Screenshot cold-tab durations are not warm navigation measurements. `ui_audit.json`, `navigation_audit.json`, `interaction_audit.json` and PNGs are under `reports/screenshots/phase3a`.

Development issues and attempts remain in `data/tmp/phase3a_*`: unavailable packages, missing UI PyYAML, rejected-view key mismatch, premature screenshot hydration, browser selectors for hidden radio inputs, reset retaining the selected scenario, and repeated tariff-shape construction. These were corrected in new dashboard code/environment only. No backend policy was altered and no frozen failed physical plan was made acceptable. UI PyYAML was bootstrapped from the existing local same-version package because sandbox package downloads were blocked; standard setup declares the exact dependency.

Evidence distinction: global decision timestamp/public health state are as-of origin; day totals/curves are retrospectively replay-realized. Expected heat energy uses the existing backward-looking analytics baseline, not a new trained model. Forecasts are identified separately. QC feeder meters need not close to physical MAIN. Initial adaptive forecasts are distinct from final realized dispatch. Historical D/E/F Impact cards are separately labelled populations. PUBLIC-BENCHMARK UCI/AI4I are not plant observations.
''')
    md('phase3a_information_boundary.md',f'''# Phase III-A boundary and approval audit
PASS. UI/facade consumes immutable projected JSON, public readings/heat/production analytics and public typed DecisionPackets. No events, latent health/wear, future noise/fault tape or attribution labels enter decision inputs. Hidden worker outputs remain under explicitly evaluation-only directories; only trusted frozen backend workers hold physical replay capabilities. The browser has no simulator filesystem tool.

Current observations/history are checked against the simulated forecast origin and posting time. Frozen model/schema and same snapshot/seed/day/schedule/replay identities must match. Client freshness mirrors the frozen Phase-G 30-minute contract. Completed-day replay charts are explicitly retrospective and never treated as current prediction inputs. Failed runs do not borrow another seed's trace. Deck claims read exact source fields and hashes instead of recomputing partial historical aggregates.

Verified presentation requires optimizer feasibility, physical replay acceptance, completed production, passed independent checker with every component PASS and matching plan/replay IDs. Missing/corrupt evidence and stale/future state fail closed with sanitized operator messages. Replay rejection remains visible. Computation limits retain deterministic failure language; the UI does not interpret a solve limit as proof that no feasible plan exists.

ApprovalGateway is unchanged. Confirmation, approve/reject/defer, immutable rejection, isolated sessions and explicit demo/live audit labels are tested. A review fork retains the original hash chain through final disposition and records source audit hash; prior approvals/execution are intentionally not inherited. Unverified candidate excerpts cannot register as approved canonical decisions. Approval causes no execution. Reset creates a new session and does not erase logs. Operator notes remain data, never instructions or prompts.

{protected:,} Phase I–II-G hashes verified before and after release. Full upstream regression and dedicated dashboard boundary tests pass. Prototype operator identity is explicitly simulated; authentication and adversarial deployment hardening remain future integration work.
''')
    # Snapshot new configuration only, never alter any upstream configuration.
    write(ROOT/'dashboard/release_v1/config_snapshot.json',dict(files={p:file_hash(ROOT/p) for p in
        ['configs/dashboard_v1.yaml','.streamlit/config.toml','requirements-dashboard.lock.txt','configs/phase3a_readonly_manifest.json']}))
    assert protect()==protected
    paths=set()
    patterns=['src/energy_copilot/dashboard/*.py','dashboard/app.py','dashboard/evidence_v1/**/*.json',
        'dashboard/release_v1/config_snapshot.json','configs/dashboard_v1.yaml','configs/phase3a_readonly_manifest.json',
        '.streamlit/config.toml','requirements-dashboard*.txt','scripts/phase3a*','scripts/setup_dashboard.ps1',
        'tests/test_dashboard*.py','docs/phase3a*','reports/phase3a*','reports/screenshots/phase3a/*','dashboard_deck_metrics.json',
        'data/tmp/phase3a*']
    for pattern in patterns:paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    # Release the successful live receipt, public bundle and operational provenance;
    # private physical evaluation tables are retained in the runtime directory.
    paths.update(p for p in live_root.rglob('*') if p.is_file() and 'execution_gateway_evaluation_only' not in p.parts)
    write(RELEASE,dict(version='dashboard_v1',status=summary['status'],protected_upstream_files=protected,
        private_evaluation_retained_at=str((live_root/'execution_gateway_evaluation_only').relative_to(ROOT)),
        files={str(p.relative_to(ROOT)).replace('\\','/'):file_hash(p) for p in sorted(paths)}))
    verify()
if __name__=='__main__':main()
