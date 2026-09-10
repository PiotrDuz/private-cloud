# OpenObserve service

OpenObserve is managed by `ansible/roles/logging` through the `logging` stage.

- OpenObserve 0.90.3 uses a digest-pinned official image.
- It runs as one local-mode node with disk storage and SQLite metadata.
- The dataset is `tank/secure/no-backup/k0s/services/openobserve`.
- The dataset uses the configured quota and a dedicated `10Ti` PV.
- Traefik publishes the configured logging hostname over HTTPS.
- Alloy authenticates to the Loki-compatible ingestion endpoint.
- Alloy uses an ingestion-only passcode retrieved during deployment.
- Retention uses `private_cloud.logging.retention_days`.
- Ingestion payloads are limited to 10MiB.
- Queries time out after 60 seconds and return 1,000 rows by default.
- The memory circuit breaker activates at 90%.
- The notifications flag disables SMTP and all four managed alerts together.
- Severity alerts exclude OpenObserve logs to prevent notification feedback loops.
- Independent Zabbix checks report OpenObserve delivery failures.
- The Stalwart forwarding alias is the OpenObserve administrator identity and alert recipient.
- Changing that alias does not rename an existing OpenObserve administrator.

## Operations

- Search the `logs` stream in the OpenObserve UI.
- Check the host heartbeat before treating a quiet stream as healthy.
- Treat OpenObserve state and log history as disposable no-backup data.
