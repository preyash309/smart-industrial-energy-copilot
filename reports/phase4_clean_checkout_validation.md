# Clean-checkout validation

Fresh local Git clone of candidate 633b516 (same scientific tree as 54b1369, plus .gitattributes). Python 3.12.14 was created in a separate empty venv. `pip install --no-index --find-links <local wheelhouse> -r requirements-dev.txt` succeeded from 44 repacked qualified distributions; available installed-file RECORD SHA256 values were checked before packaging. `pip check`: no broken requirements. Streamlit 1.64.0 / Plotly 7.1.0 / PyYAML 6.0.3 imported from this clean environment. No network installation is claimed.

`python scripts/verify_release.py --tests`: **43 passed in 6.90 s**, covering four coherent scenarios × seven screens, evidence/schema/posting-time, approval/reset/rejection and packaging. `python examples/demo_decision.py` produced PRECOMPUTED VERIFIED DEMO, VERIFIED_RECOMMENDATION and operator status VERIFIED (no automatic approval). `python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8503 --server.headless true` started and bound the local server.

The first clone exposed Git automatic line-ending conversion as a release-blocking hash defect. New `.gitattributes` disables conversion; a fresh clone passed every selected-source/bundle/metric hash. No scientific byte was changed to accommodate Git. The failed initial check is retained in local session history; it was not described as a pass.

A fresh interactive browser check was denied by browser security policy. No alternate browser/workaround was attempted; no new browser screenshot is claimed. All original Streamlit AppTest cases ran on the clean clone, and the frozen Phase III-A visual audits/screenshots remain unchanged.

Scientific subset using the separately qualified scientific environment: **224 passed in 28.83 s**. Full original archive: **492 passed, 1 skipped in 378.90 s**. UI skip is intentional environment isolation, covered by the 43-test UI/public job. Full protected archive check passed 9,954 upstream + 99 dashboard files. Remote GitHub Actions installation/status is separate from these local equivalent test commands.
