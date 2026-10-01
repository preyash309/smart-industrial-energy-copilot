# Phase IV pre-release audit

Recorded before public packaging. The research directory has no Git repository: status, branch, HEAD and remotes are unavailable. A new, separate public checkout is required; there is no existing history to rewrite. Owner authorization now includes creating a new GitHub repository and pushing the audited release.

Protected verification: `PYTHONPATH=src;. .venv/Scripts/python.exe scripts/phase3a_release.py --verify` reported **99 dashboard files and 9,954 upstream files unchanged**.

Full regression: `.venv/Scripts/python.exe -m pytest -q` with `PYTHONPATH=src;.` reported **492 passed, 1 skipped in 136.46 s**. The UI module is intentionally absent from the scientific environment. Original log: `data/tmp/phase4_pre_tests.log`.

README.md, CHANGELOG.md, pyproject.toml and scientific dependency locks are themselves protected. They will remain unchanged in the research archive; the public product will have separate v1.0.0 packaging metadata. Scientific simulator version remains sim_v1.1. No parameter, result, model, failed case, test or runtime service is to be changed.

Inventory and reverse references: `phase4_repository_inventory.json`; human summary: `phase4_repository_inventory.md`. The archive is retained in place. Exclusion of environments, caches and bulk experiments from Git is not deletion of evidence. The lightweight public profile will explicitly document which historical tests require the full archive.

Initial privacy scan found no likely credentials in non-environment text. Historical machine paths are catalogued in `phase4_security_scan.json`; machine-specific capture helpers are not public runtime. A second audit of the exact public selection is required before upload.

License: no existing project license was found. Owner selection remains pending; no third-party redistribution permission is invented. Supplied challenge PDFs stay in the original archive. Public UCI/AI4I dataset attribution must remain separate from simulated reference-plant evidence.
