# Phase-IV large-file audit
Threshold counts (including local installed environments): {10: 9, 50: 0, 100: 0}. File sizes use MiB. Environments/corpora/bulk replay evidence stay local and are excluded from the public profile. Required ledger files remain retained; no sole copy is deleted. Public profile size and >10/50/100 MiB findings will be reported after construction.

| File | MiB | Handling |
|---|---:|---|
| `.venv/Lib/site-packages/pyarrow/arrow.dll` | 21.43 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv-dashboard/Lib/site-packages/pyarrow/arrow.dll` | 20.98 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv-dashboard/Lib/site-packages/numpy.libs/libscipy_openblas64_-ed4f167a5330424524f45258e7ca2c8d.dll` | 19.64 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv/Lib/site-packages/numpy.libs/libscipy_openblas64_-9e3e5a4229c1ca39f10dc82bba9e2b2b.dll` | 19.46 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv/Lib/site-packages/scipy.libs/libscipy_openblas-64eda39e79589aedb16f58e5547eb599.dll` | 19.32 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv-dashboard/Lib/site-packages/pydeck/nbextension/static/index.js.map` | 18.51 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv-dashboard/share/jupyter/nbextensions/pydeck/index.js.map` | 18.51 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv-dashboard/Lib/site-packages/pyarrow/arrow_flight.dll` | 13.98 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
| `.venv/Lib/site-packages/pyarrow/arrow_flight.dll` | 12.78 | RETAIN ARCHIVE / DO NOT COMMIT BULK |
