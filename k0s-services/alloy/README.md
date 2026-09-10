# Alloy service

Alloy is managed by `ansible/roles/logging` through the `logging` stage.

- Alloy 1.19.2 uses a digest-pinned image.
- It runs in `observability` with experimental stability enabled.
- It reads the kubelet pod-log directory read-only at `/var/log/pods`.
- The host source is `/tank/secure/k0s/kubelet/logs` in the ephemeral k0s dataset.
- It also reads the persistent host journal and Kubernetes events.
- The dataset is `tank/secure/no-backup/k0s/services/alloy`.
- The dataset uses the configured quota and a dedicated `10Ti` PV.
- Persistent storage keeps source positions and the write-ahead log.
- An OpenObserve ingestion passcode keeps the administrator password out of Alloy.

## Configuration and limits

- Set `private_cloud.logging.alloy_storage_size` for the dataset quota.
- Set `private_cloud.logging.alloy_max_ram` for the container memory limit.
- The write-ahead log has a six-hour maximum segment age.
- Retries use a one-second to 30-second backoff with 120 attempts.
- Collection is best effort during source rotation, crashes, and prolonged OpenObserve outages.
- Container, journal, qBittorrent, OnlyOffice, and FFmpeg retention are configured independently of Alloy.

## Severity parsing

- Parse structured levels, timestamped PostgreSQL and Rust logs, and Immich console prefixes.
- Use `unknown` for unclassified messages without treating them as alert severities.
- Preserve the Kubernetes timestamp when the source has no parsed application timestamp.

## Operations

- Check the host heartbeat before treating a quiet stream as healthy.
- Check source positions and write-ahead-log growth before the Alloy quota fills.
- Verify collection resumes after an Alloy restart and a bounded OpenObserve outage.
