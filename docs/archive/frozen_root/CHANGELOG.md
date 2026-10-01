# Changelog

## sim_v1.1 / package 1.1.0

Fix B01: RHF zone and flue temperature observations previously shared one multiplicative noise draw, allowing their ratio to cancel sensor error and recover hidden fouling severity essentially exactly. Each sensor now uses its own stable seed-derived named Generator stream, generated before decisions, at the unchanged configured noise scale. Physical zone/flue temperatures, fouling progression, fuel consumption, production, faults, accounting and all unrelated observations remain unchanged.

Add legacy-attack, residual-independence, retained-signal, stream-isolation, exact-physics and replay regression gates. The reviewed successor records boundary/independent accounting checks, 30 additional seeds, provenance and replay evidence. `sim_v1.0` and its historical audit remain immutable. Existing audit warnings are unchanged; this patch includes no Phase-II work or recalibration.
