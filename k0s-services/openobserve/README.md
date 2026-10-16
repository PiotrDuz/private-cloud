# OpenObserve service

OpenObserve is managed by `ansible/roles/logging` through the `logging` stage.

- OpenObserve 0.90.3 uses a digest-pinned official image.
- It runs as one local-mode node with disk storage and SQLite metadata.
- The dataset is `tank/secure/no-backup/k0s/services/openobserve`.
- The dataset uses the configured quota and a dedicated `10Ti` PV.
- Traefik publishes the configured logging hostname over HTTPS.
- Alloy authenticates to the Loki-compatible ingestion endpoint.
- Alloy uses an ingestion-only passcode retrieved during deployment.
- The `openobserve-admin` Secret holds the root credentials and only OpenObserve reads it.
- The `openobserve-ingest` Secret holds the ingestion passcode and only Alloy reads it.
- Retention uses `private_cloud.logging.retention_days`.
- Ingestion payloads are limited to 10MiB.
- Queries time out after 60 seconds and return 1,000 rows by default.
- The memory circuit breaker activates at 90%.
- The notifications flag disables SMTP and all four managed alerts together.
- Log alerts are throttled event notifications without recovery or reminder emails.
- Each rule suppresses repeats for sixty minutes across all services.
- The missing-heartbeat rule is an SQL aggregate that returns a row only when the heartbeat count is zero.
- Alert emails go directly to Stalwart's internal service on TCP `2525` without SMTP credentials or TLS.
- Severity alerts exclude OpenObserve logs to prevent notification feedback loops.
- Zabbix does not probe OpenObserve health, metrics, internal logs, or heartbeat searches.
- OpenObserve reports missing host heartbeats through its own managed alert.
- The Stalwart forwarding alias is the OpenObserve administrator identity and alert recipient.
- Changing that alias does not rename an existing OpenObserve administrator.

## Operations

- Search the `logs` stream in the OpenObserve UI.
- Check the host heartbeat before treating a quiet stream as healthy.
- Inspect OpenObserve internal logs and notification failures directly during delivery incidents.
- Treat OpenObserve state and log history as disposable no-backup data.
