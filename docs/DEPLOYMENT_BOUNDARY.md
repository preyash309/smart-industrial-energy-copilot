# Deployment boundary

v1.0 is a simulation and decision-support prototype for local demonstrations. It is not safety-certified control software or autonomous plant control. The UI has no PLC interface, real sensor ingestion, industrial authentication, cloud deployment or actual electricity billing. The unauthenticated prototype operator identity is explicitly simulated. Do not expose the local dashboard as a production service.

Future deployment requires plant-specific sensor/measurement validation, field calibration, secure ingestion, authentication/RBAC, service/process isolation, audit retention, operational security review, real tariff integration and supervised operator trials. Production/maintenance safety remains under qualified plant authority. Empirical uncertainty quantiles and reduced-order replay are not industrial safety guarantees.

Approved future additions are offline/versioned; the supervisor cannot self-modify physics, constraints, thresholds, models or tool definitions. A live LLM would need independent G1 qualification. The deterministic v1.0 backend remains sufficient for the current checked workflow.
