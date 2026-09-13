# Infrastructure and service plan

This file defines the wanted target state; it does not certify implementation or deployment.
Outstanding implementation, operator setup, and acceptance checks are tracked in [TODO.md](TODO.md).

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
    4. Default service datasets to tank/secure/backup/k0s/services and place disposable logging data under tank/secure/no-backup/k0s/services
    5. install k0s
    6. make sure k0s starts after zfs is mounted and unlocked on system startup
    7. Set explicit quotas for config, images, and ephemeral leaf datasets
    8. Keep Kubernetes manifests as Jinja templates under k0s-services and render them directly with Ansible.
    9. Load the Intel i915 driver and install the matching firmware for integrated graphics
    10. Deploy the Intel Kubernetes GPU plugin with shared allocations for machine learning and media workloads
    11. Run one combined controller and worker with kube-router networking
    12. Pin the k0s version and checksum in the owning role
    13. Use node-bound local storage and single-writer workloads on this single-host cluster
    14. Store container logs under /tank/secure/k0s/kubelet/logs in the quota-controlled ephemeral kubelet dataset.
    15. Rotate container logs as five 10Mi files per container.
    16. Bound the persistent host journal to 1GiB and seven days initially.
    17. Keep CPU requests and memory limits without CPU limits for all Kubernetes containers.
3. Setup postgres service (in k0s-services parent folder)
    1. create postgres zfs dataset under tank/secure/backup/k0s/services/postgres
    2. Tune dataset and postgres config. Use URL as a reference, but implement only the features mentioned below: https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers
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
    3. postgres service with its own Kubernetes volume linked with dataset is deployed in k0s
    4. Use the TensorChord PostgreSQL 18 image and verify pgvector and VectorChord
    5. Disable the file collector and send PostgreSQL logs to stderr with an explicit timestamp and process prefix.
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
    10. Email Warning, Average, High, and Disaster problems through the configured relay when notifications are enabled.
    11. Use native stdout/stderr for Zabbix containers.
    12. Route Zabbix Agent and host collector diagnostics through system logging, the journal, and Alloy into OpenObserve.
    13. Keep ZFS, ECC, and SMART metric results in Zabbix while forwarding collector failures as logs.
5. Setup MEILISEARCH
    1. Create a Meilisearch dataset under tank/secure/backup/k0s/services/meilisearch with a quota
    2. Deploy Meilisearch in k0s with its own 10Ti PV
    3. Enable native JSON stderr logging for collection by Alloy.
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
    15. Configure the inbox.eu SMTP relay.
        - Deliver local-domain mail locally and route other outbound mail through inbox.eu.
        - Use the configured relay hostname, port, username, and implicit TLS or STARTTLS mode.
        - Reject invalid relay certificates.
        - Supply the relay password through the Stalwart runtime Secret.
        - Use the same relay settings for Zabbix and OpenObserve notification delivery.
        - Use the configured notification sender address for alert emails.
        - Address alerts to `<stalwart.mailbox_username>@<stalwart.forwarding_domain>`.
        - Route alert delivery through the forwarding-domain MX and Traefik TCP 25 to Stalwart.
        - Deliver the forwarding alias into `<stalwart.mailbox_username>@<stalwart.domain>`.
        - Restrict notification SMTP egress to the relay IPv4 addresses resolved when policies are applied.
    16. Support JMAP access, SMTP forwarding, filtering, outbound relay, and automatic certificate renewal
    17. Use native stdout/stderr logging for collection by Alloy.
7. Setup APACHE TIKA
    1. Create an Apache Tika dataset under tank/secure/backup/k0s/services/tika with a quota
    2. Deploy Apache Tika in k0s with its own 10Ti PV
    3. Use native stdout/stderr logging for collection by Alloy.
8. Setup BLEVE
    1. Create a Bleve dataset under tank/secure/backup/k0s/services/bleve with a quota
    2. Create a dedicated 10Ti PV for the embedded OpenCloud Bleve search backend
    3. Collect embedded Bleve search logs through the OpenCloud container.
9. Setup ONLYOFFICE
    1. Create an OnlyOffice dataset under tank/secure/backup/k0s/services/onlyoffice with a quota
    2. Deploy OnlyOffice Community Edition in k0s with its own 10Ti PV
    3. Enable the OnlyOffice WOPI integration
    4. Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
    5. Use OnlyOffice 9.4.0.1's native entrypoint to forward /var/log/onlyoffice to container output without a logging sidecar.
    6. Persist source logs on the OnlyOffice dataset.
    7. Check source rotation every 15 minutes with a 10MiB limit and seven-day retention.
    8. Run container root inside a Kubernetes user namespace.
10. Setup OPENCLOUD
    1. Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
    2. Configure OpenCloud to use Apache Tika for content extraction
    3. Configure the search service to use the Bleve backend
    4. Configure supported cache stores to use in-memory storage
    5. Configure the file storage to use filesystem storage on the OpenCloud PV
    6. Enable the built-in collaboration service and connect it to OnlyOffice
    7. Install and configure the Draw.io web extension
    8. Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
    9. Use native stdout/stderr logging for collection by Alloy.
11. Setup GRIST
    1. Deploy Grist with its own dataset under tank/secure/backup/k0s/services/grist, 10Ti PV, and quota
    2. Create a Grist database, login role, and credentials Secret in the existing postgres service
    3. Persist Grist documents on its PV and isolate formulas with Pyodide
    4. Expose Grist for the user-provided domain through a valid TLS reverse proxy
    5. Use native stdout/stderr logging for collection by Alloy.
12. Setup MANTICORE SEARCH
    1. Create a Manticore Search dataset under tank/secure/backup/k0s/services/manticore with a quota
    2. Deploy Manticore Search in k0s with its own 10Ti PV
    3. Use native stdout/stderr logging for collection by Alloy.
13. Setup REDIS for AFFiNE
    1. Deploy `redis-affine` as an independent k0s service for AFFiNE
    2. Keep Redis data ephemeral without a dataset, PV, or PVC
    3. Restrict Redis ingress to the AFFiNE server and database preparation Job
    4. Use native stdout/stderr logging for collection by Alloy.
14. Setup AFFINE
    1. Deploy AFFiNE with its own dataset under tank/secure/backup/k0s/services/affine, 10Ti PV, and quota
    2. Create an AFFiNE database with pgvector enabled in the shared PostgreSQL service
    3. Configure the server-side indexer to use Manticore Search
    4. Use the independent `redis-affine` service
    5. Prepare the fresh AFFiNE database schema before the server starts
    6. Persist AFFiNE blobs and configuration on its PV
    7. Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
    8. Use native stdout/stderr logging for collection by Alloy.
    9. Run container root inside a Kubernetes user namespace.
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
    10. Use native stdout/stderr logging for collection by Alloy.
    11. Run container root inside a Kubernetes user namespace.
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
    14. Use router forwarding for public entry and split DNS for LAN and VPN application access
    15. Place application services, their databases, search dependencies, and Zabbix in private-cloud.
    16. Place Sonarr, Radarr, Prowlarr, qBittorrent, the OpenVPN gateway, and Jellyfin in media.
    17. Place Traefik in edge, AmneziaWG in network-access, and Cloudflare DDNS in dns-system.
    18. Place Alloy and OpenObserve in observability.
    19. Keep CNI, cluster DNS, and the GPU device plugin in kube-system.
    20. Keep ZFS, the host firewall, Zabbix Agent, and journal collection support on the host.
    21. Label managed namespaces and enforce default-deny ingress and egress with explicit exceptions.
    22. Permit application dependencies only through declared service ports and namespace selectors.
    23. Restrict AmneziaWG peers to approved LAN destinations and public Internet forwarding.
    24. Deny AmneziaWG peer access to other peers, pod CIDRs, service CIDRs, and media APIs.
    25. Use split DNS and the internal Traefik address for OpenCloud and OnlyOffice callbacks.
    26. Give Traefik a quota-controlled backup dataset and a dedicated 10Ti PV/PVC.
    27. Enable structured Traefik service and access logs on stdout.
    28. Disable the Traefik dashboard and leave unknown HTTPS hosts without a route.
    29. Keep DDNS credentials separate from Traefik and Stalwart certificate credentials.
    30. Maintain the permitted connection matrix in [NETWORKING.md](docs/NETWORKING.md).
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
    10. Connect Prowlarr, Sonarr, Radarr, and qBittorrent automatically with native API keys and a Vault-managed qBittorrent password
    11. Keep Sonarr, Radarr, Prowlarr, OpenVPN, and network helpers on native console output.
    12. Enable qBittorrent file logging and forward /config/qBittorrent/logs/qbittorrent.log through the file-logs sidecar.
    13. Mount qBittorrent source logs read-only in the sidecar and persist read positions on its dataset.
    14. Start the logging sidecar before qBittorrent and stop it after the application.
    15. Rotate qBittorrent source logs at 10MiB and remove them after seven days.
    16. Use Recreate deployments to prevent overlapping log checkpoint writers.
    17. Pin the OpenVPN endpoint to a literal IP and allow only its transport outside the tunnel.
    18. Route external DNS through the VPN and cluster-local DNS through cluster DNS.
    19. Disable guarded media IPv6 until equivalent capture and filtering exist.
    20. Configure /media/tv and /media/movies as ARR root folders.
    21. Collect separate 720p, 1080p, or 2160p preferences for Sonarr and Radarr during initial configuration.
    22. Create or update a `private-cloud` quality profile in each application during installation.
    23. Allow standard HDTV, WEB, and Blu-ray qualities from 720p through the selected resolution.
    24. Exclude remux, raw, disc, and low-quality theatrical sources.
    25. Use Blu-ray at the selected resolution as the automatic upgrade cutoff.
    26. Select the `private-cloud` profile when adding series or movies and configuring import lists.
    27. Select indexer providers and credentials during operator setup.
18. Setup JELLYFIN
    1. Keep Jellyfin templates under k0s-services/jellyfin
    2. Deploy Jellyfin in the media namespace through the media installer stage
    3. Create a Jellyfin dataset under tank/secure/backup/k0s/services/jellyfin with a quota and a dedicated 10Ti PV
    4. Mount the shared media library read-only
    5. Use one shared Intel i915 GPU allocation for transcoding
    6. Expose the configured hostname through Traefik HTTPS
    7. Accept connections only from Traefik and deny Jellyfin-initiated network traffic
    8. Apply local-only library settings and disable plugin repositories before Jellyfin starts.
    9. Keep online metadata, subtitle, plugin, and remote-media integrations disabled
    10. Use native console logging without a logging sidecar
    11. Keep separate FFmpeg diagnostic logs on the Jellyfin dataset
    12. Prune closed FFmpeg diagnostics after seven days or above 1GiB while preserving active files.
19. Setup ALLOY LOG COLLECTION
    1. Deploy digest-pinned Grafana Alloy 1.19.2 as one node collector in observability.
    2. Create tank/secure/no-backup/k0s/services/alloy with a configurable 5G initial quota and dedicated 10Ti PV/PVC.
    3. Persist source positions and write-ahead buffers as disposable data.
    4. Read Kubernetes CRI files through read-only host mounts and narrowly scoped discovery RBAC.
    5. Collect workload containers, init containers, sidecars, host journal entries, and Kubernetes events.
    6. Retain journal records for the kernel, k0s, ZFS, SSH, Zabbix Agent, and logging heartbeat.
    7. Keep applications on native stdout/stderr wherever supported.
    8. Use file-forwarding sidecars only for logs unavailable on stdout/stderr.
    9. Preserve source timestamps, parse CRI framing, and join multiline exceptions.
    10. Parse structured severity fields and known console formats, including qBittorrent's wrapped messages.
    11. Normalize warning, error, fatal, panic, and critical levels before alert evaluation.
    12. Preserve unclassified messages without assigning an alert level.
    13. Index only namespace, service, container, node, job, and severity labels.
    14. Keep request IDs, filenames, email addresses, and message text out of indexed labels.
    15. Redact credentials, authorization headers, cookies, and mail bodies before ingestion.
    16. Avoid duplicate collection through both container files and the Kubernetes log API.
    17. Authenticate Alloy with OpenObserve's ingestion-only passcode.
    18. Keep the OpenObserve administrator password out of the collector pod.
    19. Enable Alloy's persistent write-ahead log with retry backoff and finite retries.
    20. Keep the Alloy endpoint private with default-deny policies.
    21. Read media logs from the node without granting media applications new egress.
    22. Limit memory and buffering with a six-hour maximum WAL segment age.
    23. Retry ingestion up to 120 times with one-second to 30-second backoff.
    24. Keep source rotation independent of central retention and dataset quotas.
    25. Collect Zabbix Agent journal records and host collector errors identified by private-cloud-zabbix-* syslog names.
20. Setup OPENOBSERVE AND OBSERVABILITY
    1. Deploy one digest-pinned OpenObserve 0.90.3 node in observability.
    2. Create tank/secure/no-backup/k0s/services/openobserve with a configurable 50G initial quota and dedicated 10Ti PV/PVC.
    3. Use OpenObserve local mode with disk object storage and SQLite metadata.
    4. Retain logs for 14 days through OpenObserve compaction.
    5. Keep OpenObserve state and log history in disposable no-backup storage.
    6. Expose OpenObserve through an exact Traefik HTTPS hostname with authentication required.
    7. Enforce memory limits, 10MiB ingestion payloads, and 60-second query timeouts.
    8. Return 1,000 query rows by default and activate the memory circuit breaker at 90%.
    9. Use native stdout/stderr logging for collection by Alloy.
    10. Keep infrastructure metric alerts in Zabbix and recognized log alerts in OpenObserve.
    11. Provision three severity rules and one missing-heartbeat rule in the logs stream.
    12. Evaluate each rule every minute over the preceding five minutes.
    13. Trigger severity alerts on at least one warn, error, or critical entry without an additional pending period.
    14. Include Kubernetes Warning events and classify Traefik HTTP 5xx responses as errors.
    15. Suppress repeated notifications from each rule for five minutes.
    16. Exclude OpenObserve's own logs from severity alerts to prevent notification feedback loops.
    17. Trigger the missing-heartbeat rule when no host logging heartbeat appears in the five-minute window.
    18. Disable OpenObserve SMTP and all four managed rules when notifications are disabled.
    19. Include the alert name, matching row count, severity, namespace, service, message, and investigation link in log emails.
    20. Send Zabbix problem, recovery, and hourly reminder emails to the forwarding alias.
    21. Retry Zabbix email delivery up to ten times at one-minute intervals.
    22. Pause Zabbix notifications for suppressed problems during maintenance.
    23. Warn on service dataset quota utilization at 80% and raise high alerts at 90% through Zabbix.
    24. Check enabled HTTPS and Stalwart SMTP STARTTLS certificates through Zabbix with expiry alerts at 21 and 7 days.
    25. Keep log alert delivery dependent on OpenObserve, the external relay, DNS, inbound SMTP, and the local mailbox services.
    26. Keep OpenObserve health, metrics, internal warnings, and heartbeat searches outside Zabbix application probes.
    27. Keep Alloy health, retry, and dropped-entry monitoring in Zabbix.
    28. Keep shared dataset capacity and edge certificate monitoring separate from OpenObserve application health probes.
    29. Keep OpenObserve's internal logs searchable without sending them through its own severity email rules.
    30. Run the Zabbix Alloy and certificate collector without sudo or OpenObserve administrator credentials.
21. SECURITY
    1. Run ordinary application containers with fixed non-root UIDs and disabled privilege escalation.
    2. Run AFFiNE, Immich server, and OnlyOffice container root inside Kubernetes user namespaces.
    3. Map user-namespaced root to an unprivileged host UID.
    4. Preserve the container startup capabilities required by AFFiNE and OnlyOffice inside their user namespaces.
    5. Drop Linux capabilities except for workload-specific startup and networking requirements.
    6. Retain NET_RAW for Zabbix ICMP checks and NET_BIND_SERVICE for services binding privileged ports.
    7. Reserve host access and network administration for networking, GPU support, and log collection workloads.
    8. Run Alloy with root read access to host logs through read-only mounts and with all capabilities dropped.
    9. Align persistent dataset ownership with each workload's UID and GID.
    10. Disable service-account token automounting for applications that do not need Kubernetes API access.
    11. Limit Alloy Kubernetes API access to workload discovery and event collection.
    12. Enforce namespace default-deny policies with explicit service and port exceptions.
    13. Keep application credentials in role-owned Kubernetes Secrets and persistent plaintext secrets out of the repository.
    14. Keep ingestion credentials separate from OpenObserve administrator credentials.
    15. Keep media VPN isolation and Jellyfin egress restrictions independent of log collection.
