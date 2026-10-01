# Phase-IV pre-cleanup repository inventory
The complete machine-readable inventory and reverse-reference index are in `phase4_repository_inventory.json`. Every major directory is classified before removal/export. Immutable ledgers protect 10,054 paths; referenced provenance overrides superficial age/filename classifications. No original scientific file has been moved or deleted.

| Major path | Files | MiB | Default treatment |
|---|---:|---:|---|
| .gitignore | 1 | 0.00 | KEEP / REVIEW |
| .streamlit | 1 | 0.00 | KEEP / REVIEW |
| .venv | 16047 | 500.06 | REMOVE FROM PUBLIC / KEEP LOCAL |
| .venv-dashboard | 14140 | 404.35 | REMOVE FROM PUBLIC / KEEP LOCAL |
| CHANGELOG.md | 1 | 0.00 | KEEP / REVIEW |
| Datasets | 2 | 3.10 | ARCHIVE |
| README.md | 1 | 0.01 | KEEP / REVIEW |
| Readme | 5 | 0.38 | ARCHIVE |
| configs | 24 | 3.84 | KEEP |
| dashboard | 10 | 1.75 | KEEP |
| dashboard_deck_metrics.json | 1 | 0.02 | KEEP / REVIEW |
| data | 1259 | 185.84 | ARCHIVE / KEEP SELECTED |
| docs | 13 | 0.04 | CONSOLIDATE |
| models | 74 | 7.53 | KEEP SELECTED / ARCHIVE |
| plans | 56 | 11.78 | ARCHIVE / KEEP SELECTED |
| predictions | 3 | 1.07 | ARCHIVE / KEEP SELECTED |
| pyproject.toml | 1 | 0.00 | KEEP / REVIEW |
| replay | 7307 | 527.61 | ARCHIVE / KEEP SELECTED |
| reports | 137 | 7.04 | KEEP SELECTED / ARCHIVE |
| reports.zip | 1 | 1.12 | KEEP / REVIEW |
| requirements-dashboard.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements-dashboard.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements-phase2b.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements-phase2c.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements-phase2f.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements-phase2g.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements.lock.txt | 1 | 0.00 | KEEP / REVIEW |
| requirements.txt | 1 | 0.00 | KEEP / REVIEW |
| scripts | 56 | 0.86 | KEEP SELECTED / ARCHIVE |
| src | 182 | 1.57 | KEEP |
| supervision | 1513 | 37.49 | ARCHIVE / KEEP SELECTED |
| tests | 53 | 0.91 | KEEP |
| tmp | 3 | 0.08 | ARCHIVE |

KEEP: runtime source, versioned configs, all scientific tests, selected production model artifacts, demo bundles and their audit/schema/source-evidence closure, final report summaries and split ledgers.

CONSOLIDATE: write new permanent README/methods/data/reproducibility/results/deployment/index docs; retain originals in the research archive. Root README/changelog/package metadata are themselves hash-pinned and cannot be casually overwritten. The public checkout uses new root docs/metadata; the frozen originals remain separately retained.

ARCHIVE: full simulated corpora, latent/evaluation outputs, failed cases, candidate/replay models, pilot tuning history, source PDFs, historical logs and complete provenance. They remain on disk. Exclusion from a lightweight Git checkout is not deletion and is recorded explicitly in its profile manifest.

REMOVE FROM PUBLIC: virtual environments, bytecode/cache/IDE files, local runtime jobs, duplicate `reports.zip`, machine-specific browser-capture helpers and scratch/notebook directories. No uncertain historical evidence is deleted. These are packaging exclusions, not metric/test changes.

Reference detection searches test/script/config/model/report/doc text and JSON path keys/values. Exact protected-manifest membership is authoritative even where free-text regex cannot resolve a dynamic reference. Every selected public source file receives its original SHA256 in the publication provenance map.
