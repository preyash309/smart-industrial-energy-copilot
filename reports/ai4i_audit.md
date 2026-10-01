# AI4I audit

10,000 synthetic independent machine snapshots; not this steel plant and not a longitudinal failure-warning benchmark. Target Machine failure preserved exactly; prevalence 3.39%. Zero missing rows, duplicate rows or UDI values; numeric physical features nonnegative and finite. Ranges and split class counts: ai4i_audit.json.

Fixed seed-42 stratified 70/15/15 manifest: {'test': 1500, 'train': 7000, 'validation': 1500}. Safe feature allowlist: ['Type', 'Air temperature [K]', 'Process temperature [K]', 'Rotational speed [rpm]', 'Torque [Nm]', 'Tool wear [min]']. TWF/HDF/PWF/OSF/RNF, UDI, Product ID, source_row_id and the target are prohibited as inputs. source_row_id is an audit/join key only. Failure-type OR differs from the preserved target in 27 rows; do not rewrite the target from these columns. No classifier trained.
