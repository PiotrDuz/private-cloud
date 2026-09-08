# Infrastructure and service plan

This file records the target architecture and major repository decisions. Repository configuration does not establish that a system is deployed or verified.

| Area | Repository status |
| --- | --- |
| Storage, k0s, application services, networking, media, and host monitoring | Installation roles and manifests exist. |
| Application logging | Console logging and the qBittorrent file forwarder exist; coverage and rotation need completion. |
| Loki, Alloy, Grafana, and email notifications | Planned below; no deployment or notification configuration exists yet. |
| Independent backups and external outage monitoring | Operator work; automation is not implemented. |

## Existing infrastructure and services

1. ZFS install (folder zfs)
    1. Setup disks into raidz1, root = "tank"
    2. Encrypt tank/secure with AES-256-GCM and a recoverable passphrase file
    3. Give tank/secure all available pool capacity without a quota or reservation
    4. Create tank/secure/backup and tank/secure/no-backup datasets
    5. Schedule monthly scrubs
    6. Enable auto trims
    7. Unlock and mount at startup through native ZFS systemd integration and ZED mount caches
    8. Use ashift=12, zstd compression, POSIX ACLs, xattr=sa, and atime=off
2. Setup k0s (folder k0s)
    1. place container images under tank/secure/no-backup/k0s/images
    2. place ephemeral kubelet data under tank/secure/no-backup/k0s/ephemeral
    3. place k0s setup and configuration under tank/secure/backup/k0s/config
    4. Each current service creates its own dataset under tank/secure/backup/k0s/services
    5. install k0s
    6. make sure k0s starts after zfs is muounted and unlocked on system startup
    7. Set explicit quotas for config, images, and ephemeral leaf datasets
    8. Keep Kubernetes manifests as Jinja templates under k0s-services and render them directly with Ansible.
    9. Load the Intel i915 driver and install the matching firmware for integrated graphics
    10. Deploy the Intel Kubernetes GPU plugin with shared allocations for machine learning and media workloads
    11. Run one combined controller and worker with kube-router networking
    12. Pin the k0s version and checksum in the owning role
    13. Use node-bound local storage and single-writer workloads on this single-host cluster
3. Setup postgres service (in k0s-services parent folder)
    1. create postgres zfs dataset under tank/secure/backup/k0s/services/postgres
    2. Tune dataset and postgres config. Use URL as a reference, but implement only featured mentioned below: https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers
        - Setting recordsize to 8k
        - Enable compression
        - Reducing read-ahead
        - Tuning primarycache: ram limits aggressive, so primarycache=all, shared_buffers=25% of user-provided maximum postgres container memory
        Postgres side:
        - Setting full_page_writes=off
        - Disable postgres checksumming
        - Disable Postgres compression
        - Tune wal_init_zero & wal_recycle
        - Setting logbias=latency (instead of logbias=throughput)
    3. postgres service with its own kubernetess volume linked with dataset is deployed in k0s
    4. Use the TensorChord PostgreSQL 18 image and verify pgvector and VectorChord
4. Setup ZABBIX
    1. Run zabbix metrics gatherer on host (install, make sure it starts with system)
        - zfs errors
        - scrubs run
        - fixed leaf dataset size, quota, and quota utilization
        - total pool size
        - SMART disk metrics
        - system general performance (ram, cpu)
        - RAM ECC corrected and uncorrected errors
        - old snapshots, large snapshots
    2. Deploy Zabbix server with its own dataset, quota, and 10Ti PV in the cluster
    3. Zabbix service creates its database, login role, and credentials Secret
    4. Connect zabbix to database
    5. expose zabbix server port so it can be connected with metrics gatherer on host
    6. WARNINGS:
        - Warn when tank usage exceeds 80% and raise a high alert above 90%
        - Raise a high alert when a fixed leaf dataset reaches 90% of its quota
        - alert on SMART disk low health
        - alert on unfixed zfs error
        - warning on zfs error that has been fixed (scrub or normal operation)
        - alert on unfixed ECC error
        - warning on ECC error that has been fixed
    7. Link active Linux, SMART, ZFS, and ECC templates to private-cloud-zabbix
    8. Maintain the Dataset capacity dashboard from the enabled dataset catalog
    9. Alert on stale collectors, old snapshots, overdue scrubs, and unavailable ECC telemetry
    10. Email every Warning, Average, High, and Disaster problem using the notification design below
5. Setup MEILISEARCH
    1. Create a Meilisearch dataset under tank/secure/backup/k0s/services/meilisearch with a quota
    2. Deploy Meilisearch in k0s with its own 10Ti PV
6. Setup STALWART email
    1. Deploy Stalwart with its own dataset under tank/secure/backup/k0s/services/stalwart, 10Ti PV, and quota
    2. Create a Stalwart database, login role, and credentials Secret in the existing postgres service
    3. Configure the data store to use the Stalwart postgres database
    4. Configure the blob store as filesystem storage on the Stalwart PV
    5. Configure the search store to use Meilisearch
    6. Configure the Default in-memory store to use the postgres data store
    7. Configure Stalwart as the mailbox and JMAP submission service for the user-provided domain
    8. Publish JMAP, web access, and management through Traefik HTTPS TCP 443
    9. Accept forwarded inbound mail through Traefik SMTP TCP 25 with Proxy Protocol v2
    10. Terminate SMTP STARTTLS in Stalwart with an automatically renewed certificate
    11. Use Let's Encrypt DNS-01 and a dedicated Cloudflare token for the Stalwart certificate
    12. Keep IMAPS 993 and submission ports 465 and 587 unexposed
    13. Filter forwarded messages in Stalwart without source-CIDR restrictions at the host firewall
    14. Map forwarding-subdomain recipients to primary-domain Stalwart accounts
    15. Store inbox.eu credentials in a Secret and relay non-local outbound mail through its SMTP service over TLS
    16. Verify JMAP access, SMTP forwarding, filtering, outbound relay, and certificate renewal
7. Setup APACHE TIKA
    1. Create an Apache Tika dataset under tank/secure/backup/k0s/services/tika with a quota
    2. Deploy Apache Tika in k0s with its own 10Ti PV
8. Setup BLEVE
    1. Create a Bleve dataset under tank/secure/backup/k0s/services/bleve with a quota
    2. Create a dedicated 10Ti PV for the embedded OpenCloud Bleve search backend
9. Setup ONLYOFFICE
    1. Create an OnlyOffice dataset under tank/secure/backup/k0s/services/onlyoffice with a quota
    2. Deploy OnlyOffice Community Edition in k0s with its own 10Ti PV
    3. Enable the OnlyOffice WOPI integration
    4. Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
10. Setup OPENCLOUD
    1. Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
    2. Configure OpenCloud to use Apache Tika for content extraction
    3. Configure the search service to use the Bleve backend
    4. Configure supported cache stores to use in-memory storage
    5. Configure the file storage to use filesystem storage on the OpenCloud PV
    6. Enable the built-in collaboration service and connect it to OnlyOffice
    7. Install and configure the Draw.io web extension
    8. Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
11. Setup GRIST
    1. Deploy Grist with its own dataset under tank/secure/backup/k0s/services/grist, 10Ti PV, and quota
    2. Create a Grist database, login role, and credentials Secret in the existing postgres service
    3. Persist Grist documents on its PV and isolate formulas with Pyodide
    4. Expose Grist for the user-provided domain through a valid TLS reverse proxy
12. Setup MANTICORE SEARCH
    1. Create a Manticore Search dataset under tank/secure/backup/k0s/services/manticore with a quota
    2. Deploy Manticore Search in k0s with its own 10Ti PV
13. Setup REDIS for AFFiNE
    1. Deploy `redis-affine` as an independent k0s service for AFFiNE
    2. Keep Redis data ephemeral without a dataset, PV, or PVC
    3. Restrict Redis ingress to the AFFiNE server and database preparation Job
14. Setup AFFINE
    1. Deploy AFFiNE with its own dataset under tank/secure/backup/k0s/services/affine, 10Ti PV, and quota
    2. Create an AFFiNE database with pgvector enabled in the shared PostgreSQL service
    3. Configure the server-side indexer to use Manticore Search
    4. Use the independent `redis-affine` service
    5. Prepare the fresh AFFiNE database schema before the server starts
    6. Persist AFFiNE blobs and configuration on its PV
    7. Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
15. Setup IMMICH
    1. Deploy Immich with its own dataset under tank/secure/backup/k0s/services/immich, 10Ti PV, and quota
    2. Create an Immich database, login role, and credentials Secret in the existing PostgreSQL service
    3. Install and verify pgvector and VectorChord in the shared PostgreSQL service
    4. Enable pgvector, VectorChord, and earthdistance in the Immich database
    5. Deploy a disposable Valkey service for Immich background jobs
    6. Deploy the Immich machine-learning service for face detection and recognition
    7. Enable Intel OpenVINO acceleration through the shared i915 Kubernetes device resource
    8. Persist the Immich media library on its PV
    9. Expose Immich for the user-provided domain through a valid TLS reverse proxy
16. Setup NETWORKING
    1. Deploy Traefik with host TCP 443 for HTTPS and host TCP 25 for SMTP
    2. Publish application services as ClusterIP endpoints behind exact Traefik host rules
    3. Obtain Traefik HTTPS certificates with Cloudflare DNS-01
    4. Proxy SMTP TCP 25 to Stalwart without terminating STARTTLS
    5. Maintain configured public A records with a dedicated Cloudflare DDNS token
    6. Restrict SSH, the Kubernetes API, and Zabbix TCP 31051 to local networks
    7. Permit only TCP 443, TCP 25, and the AmneziaWG UDP port from untrusted networks
    8. Block obsolete application NodePorts and undeclared host ports
    9. Apply default-deny NetworkPolicies with explicit service flows
    10. Install the AmneziaWG kernel module on the host
    11. Keep AmneziaWG routing, NAT, and peer ACLs inside its pod network namespace
    12. Route guarded media application egress through OpenVPN with fail-closed policies
    13. Keep Jellyfin ingress behind Traefik and deny Jellyfin-initiated network traffic
    14. Document router forwarding, split DNS, and external acceptance as operator work
17. Setup ARR STACK
    1. Keep Sonarr, Radarr, Prowlarr, qBittorrent, and OpenVPN templates under k0s-services/arr
    2. Deploy the arr stack in the media namespace through the media installer stage
    3. Give each persistent application a dataset under tank/secure/backup/k0s/services with a quota and a dedicated 10Ti PV
    4. Create the shared media-library dataset with a quota and a dedicated 10Ti PV
    5. Mount the shared library writable in Sonarr, Radarr, and qBittorrent
    6. Route external traffic and DNS through OpenVPN with per-pod tun2socks helpers
    7. Block direct Internet fallback when the VPN fails
    8. Keep dashboards, peer ports, and discovery protocols unpublished
    9. Bind qBittorrent to tun0, disable UPnP, and enable anonymous mode
    10. Configure indexers, API keys, download clients, root folders, and quality profiles after deployment
18. Setup JELLYFIN
    1. Keep Jellyfin templates under k0s-services/jellyfin
    2. Deploy Jellyfin in the media namespace through the media installer stage
    3. Create a Jellyfin dataset under tank/secure/backup/k0s/services/jellyfin with a quota and a dedicated 10Ti PV
    4. Mount the shared media library read-only
    5. Use one shared Intel i915 GPU allocation for transcoding
    6. Expose the configured hostname through Traefik HTTPS
    7. Accept connections only from Traefik and deny Jellyfin-initiated network traffic
    8. Keep online metadata, subtitle, plugin, and remote-media integrations disabled
    9. Use native console logging without a logging sidecar
    10. Keep separate FFmpeg diagnostic logs on the Jellyfin dataset

## Installation and security decisions

- Keep the Python installer as the entry point for one dependency-ordered Ansible playbook.
- Support create, update, reapply, and secret rotation for greenfield installations.
- Store public settings in YAML and secrets in Ansible Vault.
- Keep Kubernetes definitions in service-owned Jinja templates and credentials in role-owned Secret templates.
- Validate the full configuration before changing infrastructure.
- Require explicit authorization before creating a new ZFS pool.
- Give each persistent service a quota-controlled dataset and dedicated 10Ti PV/PVC.
- Default service datasets to `tank/secure/backup/k0s/services`.
- Use `tank/secure/no-backup/k0s/services` only for explicitly disposable data.
- Track each enabled dataset in the shared catalog and Zabbix inventory.
- Run applications without host root privileges and drop unnecessary capabilities.
- Use Kubernetes user namespaces for AFFiNE, Immich, and OnlyOffice container root.
- Reserve infrastructure privileges for networking, GPU support, and log collection.
- Keep namespace boundaries and permitted network flows in [NETWORKING.md](docs/NETWORKING.md).

## Central logging — planned

### Collection and coverage

- Deploy Grafana Alloy as a node log collector in a dedicated `observability` namespace.
- Read Kubernetes CRI files through read-only host mounts with minimal discovery RBAC.
- Collect all workload namespaces, init containers, sidecars, and infrastructure components.
- Collect host journal entries for the kernel, k0s, ZFS, SSH, and Zabbix Agent.
- Collect Kubernetes events once per cluster and preserve Warning events.
- Keep applications on native stdout/stderr wherever supported.
- Use file-forwarding sidecars only for logs unavailable on stdout/stderr.
- Collect qBittorrent through its existing `file-logs` container without rereading its source file.
- Audit OnlyOffice's `/var/log/onlyoffice` and forward file-only operational errors.
- Collect Jellyfin console logs and retain separate FFmpeg diagnostics locally.
- Enable structured Traefik service and access logs on stdout.
- Preserve source timestamps, parse CRI framing, and join multiline exceptions.
- Parse each application's severity format, including qBittorrent's wrapped messages.
- Normalize warning, error, fatal, panic, and critical levels before alert evaluation.
- Preserve unclassified messages and alert on parsing failures.
- Use bounded labels for cluster, namespace, service, container, node, and severity.
- Keep request IDs, filenames, email addresses, and message text out of indexed labels.
- Redact credentials, authorization headers, cookies, and mail bodies before ingestion.
- Avoid duplicate collection through both container files and the Kubernetes log API.

Use [Alloy Kubernetes collection](https://grafana.com/docs/alloy/latest/collect/logs-in-kubernetes/) and [journal collection](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.source.journal/) for the collector configuration.

### Storage, retention, and access

| Component | Deployment | Dataset | Initial quota |
| --- | --- | --- | --- |
| Loki | Single binary, one replica, replication factor 1. | `tank/secure/no-backup/k0s/services/loki` | 50G |
| Alloy | One collector on the current node with persistent positions and write-ahead buffering. | `tank/secure/no-backup/k0s/services/alloy` | 5G |
| Grafana | One replica with local SQLite state and provisioned configuration. | `tank/secure/backup/k0s/services/grafana` | 5G |

Each component receives its own 10Ti PV/PVC; quotas remain configurable. Loki history and Alloy buffers are disposable, while Grafana state is backed up.

- Use Loki TSDB schema v13 with a 24-hour index period and filesystem chunk storage.
- Retain logs for 14 days through the enabled singleton Compactor.
- Persist Loki's WAL, indexes, chunks, and Compactor working directory on its PV.
- Configure a filesystem delete-request store and verify delayed chunk deletion.
- Exclude disposable log datasets from snapshot and backup schedules.
- Enable Alloy's persistent write-ahead log with bounded retention and retry backoff.
- Alert on rejected entries, exhausted retries, dropped logs, and growing delivery lag.
- Set explicit CPU, memory, ingestion, query, and buffering limits before deployment.
- Bound kubelet container logs to five 10Mi files per container initially.
- Bound the persistent host journal to 1GiB and seven days initially.
- Configure size and age limits for qBittorrent, OnlyOffice, and FFmpeg source files.
- Keep source rotation independent of Loki retention and dataset quotas.
- Expose Grafana through an exact Traefik HTTPS hostname with anonymous access disabled.
- Keep Loki and Alloy endpoints private with default-deny policies.
- Permit only collector ingestion, Grafana queries, DNS, discovery, and monitoring flows.
- Read media logs from the node without granting media applications new egress.

Loki does not delete logs in response to low disk space; quota alerts must precede exhaustion. See [filesystem storage](https://grafana.com/docs/loki/latest/operations/storage/filesystem/), [Compactor retention](https://grafana.com/docs/loki/latest/operations/storage/retention/), and [Alloy buffering](https://grafana.com/docs/alloy/latest/reference/components/loki/loki.write/).

### Log warnings and monitoring

- Provision Grafana's Loki data source, dashboards, alert rules, and notification policy through Ansible.
- Keep Zabbix responsible for infrastructure metrics and Grafana responsible for log alerts.
- Evaluate warning-or-higher log counts every minute over the preceding five minutes.
- Fire on a count greater than zero with no pending period.
- Include every service and Kubernetes Warning event without an error-rate threshold.
- Add explicit rules for failed ACME renewals, SMTP delivery, database operations, and VPN connections.
- Classify Traefik HTTP 5xx responses as errors even without a severity field.
- Monitor Loki, Alloy, Grafana, and notification failures through Zabbix independently of Loki queries.
- Add Zabbix dataset warnings at 80% and high alerts at 90% for all service datasets.
- Monitor certificate expiry at 21 and 7 days for HTTPS and SMTP STARTTLS.
- Monitor collector heartbeats instead of treating a quiet application as a collection failure.
- Treat empty warning queries as normal only while collection health is confirmed.
- Route Grafana query failures and missing heartbeat alerts to the same email recipient.

Grafana needs explicit [No Data and Error handling](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/); an unavailable Loki must not appear healthy.

## Email warnings to the Stalwart inbox — planned

The destination is the existing Stalwart mailbox, `<stalwart.mailbox_username>@<stalwart.domain>`. Send to its existing forwarding-domain alias, `<stalwart.mailbox_username>@<stalwart.forwarding_domain>`, through the configured authenticated inbox.eu SMTP relay.

`Zabbix / Grafana → inbox.eu SMTP over TLS → forwarding-domain MX → Traefik TCP 25 → Stalwart mailbox`

- Use the configured relay hostname, port, and TLS mode with certificate verification enabled.
- Use a relay-authorized sender address and credentials stored in Vault and Kubernetes Secrets.
- Permit SMTP egress only from Zabbix server and Grafana to the configured relay destinations.
- Account for relay address changes when maintaining kube-router IP-based egress rules.
- Preserve the existing public-port policy and Stalwart Proxy Protocol path.
- Deliver to the forwarding alias directly without relying on primary-domain forwarding rules.
- Configure Zabbix's SMTP media type, recipient permissions, user media, and trigger action.
- Enable Zabbix recipient media continuously for Warning, Average, High, and Disaster severities.
- Send every new Zabbix problem and its recovery to the mailbox.
- Provision Grafana SMTP settings, an email contact point, and a default notification route.
- Send every firing Grafana alert instance and its recovery to the mailbox.
- Disable cross-alert grouping and use zero initial group wait for Grafana alerts.
- Repeat unresolved Grafana alerts every five minutes and Zabbix problems hourly.
- Include severity, source, service or host, time, event count where applicable, and investigation links.
- Retry failed notifications and expose failures in monitoring.
- Apply notification silences only during explicit operator maintenance.

“Every warning” means every warning-or-higher alert instance receives email coverage, including an isolated warning log entry. Repeated lines within an active log alert produce reminders; Grafana does not send one email per raw log line. Per-line delivery would require a separate durable event notification pipeline.

Stalwart delivery depends on this host, PostgreSQL, the external relay, DNS, and inbound SMTP reachability. Local email cannot report a complete host or mailbox outage until delivery recovers; independent outage monitoring remains operator work.

Use [Zabbix email media](https://www.zabbix.com/documentation/7.4/en/manual/config/notifications/media/email), [Zabbix recovery operations](https://www.zabbix.com/documentation/7.4/en/manual/config/notifications/action/recovery_operations), [Grafana SMTP email](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-email/), and [Grafana notification timing](https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/group-alert-notifications/) for implementation.

## Implementation and acceptance — pending

- Add logging stages, dependencies, quotas, resource limits, hostname, and notification settings to the installer contract.
- Add Loki, Alloy, and Grafana roles and service templates with pinned image versions.
- Extend namespace policies, Traefik routing, DDNS records, and the dataset monitoring catalog.
- Complete per-service logging coverage and local rotation configuration.
- Provision alert rules and SMTP routing after Stalwart and monitoring are ready.
- Confirm timestamped logs from every enabled service and host source appear in Grafana.
- Confirm collection resumes after a collector restart and a bounded Loki outage.
- Confirm source rotation and expired Loki chunk deletion reclaim space.
- Verify an isolated log warning, log error, and Kubernetes Warning each generate email.
- Verify Zabbix Warning and higher problems generate email and recovery messages.
- Verify query failure, missing heartbeat, and SMTP failure remain visible as problems.
- Confirm actual messages arrive in the Stalwart inbox rather than only reaching the relay.
- Verify logging access does not weaken media VPN or Jellyfin isolation.
- Update repository status only after configuration exists and record live acceptance separately.

## Backup and recovery decisions

- Treat `backup` as a dataset classification rather than an implemented backup schedule.
- Keep independent copies of PostgreSQL, application files, Grafana state, and k0s control-plane data.
- Coordinate database and application-file recovery points.
- Keep the encryption passphrase, Vault recovery material, and configuration outside this host.
- Define snapshot retention, backup frequency, and recovery targets before production use.
- Verify independent restores and ZFS-to-k0s startup ordering after reboot.
- Use [OPERATIONS.md](docs/OPERATIONS.md) for runtime monitoring and incident response.
