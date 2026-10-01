# Phase III-A dashboard release
**PHASE III-A COMPLETE.** Seven operator pages consume four coherent frozen demo bundles. An explicit live run also reached VERIFIED_RECOMMENDATION through unchanged G0, PredictionService, robust optimization, matched replay and the independent checker. Live G1 remains pending and is not part of this release.

Launch from `D:\Projects\Schneider Electric`:
```powershell
.venv-dashboard\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```
Open http://127.0.0.1:8501. Setup/locked dependencies and screenshot commands are in `docs/phase3a_usage.md`. Streamlit 1.64.0, Plotly 7.1.0 and PyYAML 6.0.3 run in the isolated UI environment; the original `.venv` runs all physical backend work.

Pages: Overview; Energy; Optimise; Maintenance; Decision Center; Impact; Evidence / Audit. The thin DashboardService supplies public/QC analytics, prediction summaries, optimizer schedules, replay evidence and approval operations. Page modules contain presentation, not plant decisions. The Energy forecast expander displays heat p50/p90 energy/duration and AUX-only forecasts; completed heat diagnostics are kept separate.

| Demo scenario | Seed / day | Supervisory outcome | Scope |
|---|---|---|---|
| Normal optimization | 3003 / 28 | VERIFIED_RECOMMENDATION | PRECOMPUTED VERIFIED DEMO |
| Maintenance warning | 3002 / 14 | NO_VERIFIED_RECOMMENDATION | PRECOMPUTED REJECTED DEMO |
| Replay rejection | 3001 / 7 | NO_VERIFIED_RECOMMENDATION | REJECTED CANDIDATE EXCERPT · subsequent recovery shown separately |
| Adaptive recovery | 3001 / 7 | VERIFIED_RECOMMENDATION | PRECOMPUTED VERIFIED DEMO |

Normal and adaptive cases are physically verified; the pump-maintenance candidate and retained initial duration-rejected candidate remain visible and cannot be approved. The rejection excerpt is not a new canonical supervisor decision. Missing failed-case traces stay unavailable. All pages share one selected bundle. The reference timeline is the preceding observed day from that run, not the matched tariff-cost counterfactual.

Demo evidence is precomputed and labelled. Only immutable evidence is cached. Live jobs and approvals are session-local. The real browser live test took 80.056 s, including public-state construction, optimization, replay, evidence projection and protected-file checks. Actual backend tool start/completion events drive progress. The normal live output is `data\runs\dashboard_v1\live\0e6598e27a4d4e699d214be8274d5099`; the other curated live scenarios use the same adapter but were not rerun through the UI for this release. Arbitrary seed entry is not supported by the frozen integration facade.

VERIFIED is not APPROVED. Explicit prototype-operator confirmation appends a hash-chained fork of the canonical audit; historical approval is not inherited. Approve/reject/defer and reset are tested. Rejection is immutable; reset starts a new review while preserving earlier logs. Unverified plans cannot be approved. Both simulated execution and real machinery execution are disabled in this UI. These are explicit simulated operator actions, not authenticated production identities.

Responsive real-browser audit: 18 views at 1440×900 and 1280×900, zero horizontal-overflow/render/page-error findings. Screenshots in `reports/screenshots/phase3a` include the seven pages, rejection, adaptive recovery, explicit approval and a real live result. Warm navigation across 14 transitions averaged 0.829 s, maximum 1.965 s on this machine. Cold-tab loading is separately recorded and is slower. Contiguous tariff shading fixed the initial approximately nine-second chart-build bottleneck without changing slot values.

Full command: `$env:PYTHONPATH='src;.'; .venv\Scripts\python.exe -m pytest -q`: **492 passed, 1 skipped**. The skipped module requires UI packages, intentionally absent from the frozen environment. Isolated command: `.venv-dashboard\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_dashboard_ui.py -q`: **40 passed**. Includes all four scenarios × seven screens, schema/time/boundary checks, numerical/evidence separation, approval/reset/session isolation and chart shading preservation. Browser flow additionally exercises the live button and actual backend.

All **9,954 protected upstream files are unchanged**. New code/artifacts only: `src/energy_copilot/dashboard/`, `dashboard/`, `.streamlit/config.toml`, `configs/dashboard_v1.yaml`, `configs/phase3a_readonly_manifest.json`, `requirements-dashboard*.txt`, `scripts/phase3a*`, `scripts/setup_dashboard.ps1`, `tests/test_dashboard*.py`, `docs/phase3a_usage.md`, `reports/phase3a*`, screenshots, deck metrics and new dashboard runtime outputs. Exact paths/hashes are in `dashboard/release_v1/manifest.json`.

`dashboard_deck_metrics.json` contains 30 exact released fields with source path/field/hash, unit, evidence label, population and caveat. Phase D's 2.44% electricity and 4.21% synthetic tariff reductions remain distinct matched simulated effects; E's 0/10 versus 10/10 is held-out replay evidence; F's 16 services/14 avoided failures/2 undetermined and 91.67% F0 versus 87.50% F2 feasibility are shown honestly. No field savings, industrial maintenance ROI or external-benchmark-to-plant transfer is claimed.

Remaining limits: synthetic practice/tariff/maintenance, reduced-order plant physics, snapshot-based demonstrations, missing failed-case meter traces, fixed curated live cases, unauthenticated prototype operator identity and single-host session workers. Live LLM qualification, real authentication, ingestion, PLC control, cloud deployment, tariff billing and maintenance ROI are outside scope. The local dashboard should not be exposed publicly as a production service.

Three-minute path: Overview → Energy → Optimise → Replay rejection → Adaptive recovery / approval → Maintenance → Impact → Evidence. Use labelled Demo Mode; optional live appendix is separate. Full cues are in `reports/phase3a_demo_script.md`.

Ready for **Phase III-B — Live Copilot Integration + Final Submission Packaging** as a deterministic, screenshot-ready prototype. Live G1 must still be independently qualified; this readiness statement does not certify an LLM or industrial deployment.
