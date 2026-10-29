# Alloy service

Alloy is managed by `ansible/roles/logging` through the `logging` stage.

- Alloy 1.19.2 uses a digest-pinned image.
- It runs in `observability` with experimental stability enabled.
- It reads the kubelet pod-log directory read-only at `/var/log/pods`.
- The host source is `/tank/secure/k0s/kubelet/logs` in the ephemeral k0s dataset.
- It also reads the persistent host journal and Kubernetes events.
- Host collector diagnostics use private-cloud-zabbix-* service labels derived from their syslog identifiers.
- The dataset is `tank/secure/no-backup/k0s/services/alloy`.
- The dataset uses the configured quota and a dedicated `10Ti` PV.
- Persistent storage keeps source positions and the write-ahead log.
- An OpenObserve ingestion passcode keeps the administrator password out of Alloy.
- Alloy mounts only the `openobserve-ingest` Secret.
- The journal keeps k0s, ZFS, SSH, Zabbix Agent, systemd, firewall, and heartbeat units plus kernel messages.
- The journal also keeps sudo, su, login, sshd, and systemd-logind entries under the `host-auth` service.

## Configuration and limits

- `private_cloud.logging.alloy_storage_size` sets the dataset quota.
- `private_cloud.logging.alloy_max_ram` sets the container memory limit.
- The write-ahead log has a six-hour maximum segment age.
- Retries use a one-second to 30-second backoff with 120 attempts.
- Collection is best effort during source rotation, crashes, and prolonged OpenObserve outages.
- Container, journal, qBittorrent, OnlyOffice, and FFmpeg retention are configured independently of Alloy.

## Severity parsing

- Alloy parses structured levels, timestamped PostgreSQL and Rust logs, and Immich console prefixes.
- Unclassified messages get `unknown`, which no alert treats as a severity.
- Alloy drops empty lines because OpenObserve rejects any batch that contains one.
- The Kubernetes timestamp stays when the source has no parsed application timestamp.
