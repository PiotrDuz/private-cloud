# Infrastructure and service plan

This file defines the wanted target state; it does not certify implementation or deployment.
Outstanding repository work is tracked in [TODO.md](TODO.md); operator-only setup is tracked in [docs/SETUP.md](docs/SETUP.md).

## 1. ZFS install (folder zfs)

- Setup disks into raidz1, root = `tank`
- Encrypt `tank/secure` with AES-256-GCM and a recoverable passphrase file
- Give `tank/secure` all available pool capacity without a quota or reservation
- Create `tank/secure/backup` and `tank/secure/no-backup` datasets
- Schedule monthly scrubs
- Enable auto trims
- Unlock and mount at startup through native ZFS systemd integration and ZED mount caches
- Use `ashift=12`, `zstd` compression, POSIX ACLs, `xattr=sa`, and `atime=off`

## 2. Setup k0s (folder k0s)

- Place container images under `tank/secure/no-backup/k0s/images`
- Place ephemeral kubelet data under `tank/secure/no-backup/k0s/ephemeral`
- Place k0s setup and configuration under `tank/secure/backup/k0s/config`
- Default service datasets to `tank/secure/backup/k0s/services` and place disposable logging data under `tank/secure/no-backup/k0s/services`
- Install k0s
- Make sure k0s starts after ZFS is mounted and unlocked on system startup
- Set explicit quotas for config, images, and ephemeral leaf datasets
- Keep Kubernetes manifests as Jinja templates under `k0s-services` and render them directly with Ansible
- Load the Intel i915 driver and install the matching firmware for integrated graphics
- Deploy the Intel Kubernetes GPU plugin with shared allocations for machine learning and media workloads
- Run one combined controller and worker with kube-router networking
- Pin the k0s version and checksum in the owning role
- Use node-bound local storage and single-writer workloads on this single-host cluster
- Store container logs under `/tank/secure/k0s/kubelet/logs` in the quota-controlled ephemeral kubelet dataset
- Rotate container logs as five 10Mi files per container
- Bound the persistent host journal to 1GiB and seven days initially
- Keep CPU requests and memory limits without CPU limits for all Kubernetes containers

## 3. Setup postgres service (in k0s-services parent folder)

- Create the Postgres ZFS dataset under `tank/secure/backup/k0s/services/postgres`
- Tune the dataset and Postgres configuration using the [ZFS reference](https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers) and implement only the features below
    - Set `recordsize` to 8k
    - Enable compression
    - Reduce read-ahead
    - Set `primarycache=all` and `shared_buffers` to 25% of the user-provided maximum Postgres container memory
    - Postgres side:
        - Set `full_page_writes=off`
        - Disable Postgres checksumming
        - Disable Postgres compression
        - Tune `wal_init_zero` and `wal_recycle`
        - Set `logbias=latency` instead of `logbias=throughput`
- Deploy the Postgres service with its own Kubernetes volume linked to the dataset in k0s
- Use the TensorChord PostgreSQL 18 image and verify pgvector and VectorChord
- Disable the file collector and send PostgreSQL logs to stderr with an explicit timestamp and process prefix

## 4. Setup ZABBIX

- Run the Zabbix metrics gatherer on the host and start it with the system
    - ZFS errors
    - Scrubs run
    - Fixed leaf dataset size, quota, and quota utilization
    - Total pool size
    - SMART disk metrics
    - System general performance (RAM, CPU)
    - RAM ECC corrected and uncorrected errors
    - Old snapshots, large snapshots
- Deploy the Zabbix server with its own dataset, quota, and 10Ti PV in the cluster
- Let the Zabbix service create its database, login role, and credentials Secret
- Connect Zabbix to the database
- Expose the Zabbix server port so the host metrics gatherer can connect
- Configure warnings:
    - Warn when tank usage exceeds 80% and raise a high alert above 90%
    - Raise a high alert when a fixed leaf dataset reaches 90% of its quota
    - Alert on SMART disk low health
    - Alert on unfixed ZFS error
    - Warn on a ZFS error that has been fixed (scrub or normal operation)
    - Alert on unfixed ECC error
    - Warn on an ECC error that has been fixed
- Link active Linux, SMART, ZFS, and ECC templates to `private-cloud-zabbix`
- Maintain the Dataset capacity dashboard from the enabled dataset catalog
- Alert on stale collectors, old snapshots, overdue scrubs, and unavailable ECC telemetry
- Email every Warning, Average, High, and Disaster problem through the observation and email alert design
- Use native stdout/stderr for Zabbix containers and the host journal for Zabbix Agent

## 5. Setup MEILISEARCH

- Create a Meilisearch dataset under `tank/secure/backup/k0s/services/meilisearch` with a quota
- Deploy Meilisearch in k0s with its own 10Ti PV
- Enable native JSON stderr logging for collection by Alloy

## 6. Setup STALWART email

- Deploy Stalwart with its own dataset under `tank/secure/backup/k0s/services/stalwart`, 10Ti PV, and quota
- Create a Stalwart database, login role, and credentials Secret in the existing Postgres service
- Configure the data store to use the Stalwart Postgres database
- Configure the blob store as filesystem storage on the Stalwart PV
- Configure the search store to use Meilisearch
- Configure the Default in-memory store to use the Postgres data store
- Configure Stalwart as the mailbox and JMAP submission service for the user-provided domain
- Publish JMAP, web access, and management through Traefik HTTPS TCP 443
- Accept forwarded inbound mail through Traefik SMTP TCP 25 with Proxy Protocol v2
- Terminate SMTP STARTTLS in Stalwart with an automatically renewed certificate
- Use Let's Encrypt DNS-01 and a dedicated Cloudflare token for the Stalwart certificate
- Keep IMAPS 993 and submission ports 465 and 587 unexposed
- Filter forwarded messages in Stalwart without source-CIDR restrictions at the host firewall
- Map forwarding-subdomain recipients to primary-domain Stalwart accounts
- Store inbox.eu credentials in a Secret and relay non-local outbound mail through its SMTP service over TLS
- Support JMAP access, SMTP forwarding, filtering, outbound relay, and automatic certificate renewal
- Use native stdout/stderr logging for collection by Alloy

## 7. Setup APACHE TIKA

- Create an Apache Tika dataset under `tank/secure/backup/k0s/services/tika` with a quota
- Deploy Apache Tika in k0s with its own 10Ti PV
- Use native stdout/stderr logging for collection by Alloy

## 8. Setup BLEVE

- Create a Bleve dataset under `tank/secure/backup/k0s/services/bleve` with a quota
- Create a dedicated 10Ti PV for the embedded OpenCloud Bleve search backend
- Collect embedded Bleve search logs through the OpenCloud container

## 9. Setup ONLYOFFICE

- Create an OnlyOffice dataset under `tank/secure/backup/k0s/services/onlyoffice` with a quota
- Deploy OnlyOffice Community Edition in k0s with its own 10Ti PV
- Enable the OnlyOffice WOPI integration
- Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
- Use OnlyOffice 9.4.0.1's native entrypoint to forward `/var/log/onlyoffice` to container output without a logging sidecar
- Persist source logs on the OnlyOffice dataset
- Check source rotation every 15 minutes with a 10MiB limit and seven-day retention
- Run container root inside a Kubernetes user namespace

## 10. Setup OPENCLOUD

- Deploy OpenCloud with its own dataset under `tank/secure/backup/k0s/services/opencloud`, 10Ti PV, and quota
- Configure OpenCloud to use Apache Tika for content extraction
- Configure the search service to use the Bleve backend
- Configure supported cache stores to use in-memory storage
- Configure the file storage to use filesystem storage on the OpenCloud PV
- Enable the built-in collaboration service and connect it to OnlyOffice
- Install and configure the Draw.io web extension
- Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy

## 11. Setup GRIST

- Deploy Grist with its own dataset under `tank/secure/backup/k0s/services/grist`, 10Ti PV, and quota
- Create a Grist database, login role, and credentials Secret in the existing Postgres service
- Persist Grist documents on its PV and isolate formulas with Pyodide
- Expose Grist for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy

## 12. Setup MANTICORE SEARCH

- Create a Manticore Search dataset under `tank/secure/backup/k0s/services/manticore` with a quota
- Deploy Manticore Search in k0s with its own 10Ti PV
- Use native stdout/stderr logging for collection by Alloy

## 13. Setup REDIS for AFFiNE

- Deploy `redis-affine` as an independent k0s service for AFFiNE
- Keep Redis data ephemeral without a dataset, PV, or PVC
- Restrict Redis ingress to the AFFiNE server and database preparation Job
- Use native stdout/stderr logging for collection by Alloy

## 14. Setup AFFINE

- Deploy AFFiNE with its own dataset under `tank/secure/backup/k0s/services/affine`, 10Ti PV, and quota
- Create an AFFiNE database with pgvector enabled in the shared PostgreSQL service
- Configure the server-side indexer to use Manticore Search
- Use the independent `redis-affine` service
- Prepare the fresh AFFiNE database schema before the server starts
- Persist AFFiNE blobs and configuration on its PV
- Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## 15. Setup IMMICH

- Deploy Immich with its own dataset under `tank/secure/backup/k0s/services/immich`, 10Ti PV, and quota
- Create an Immich database, login role, and credentials Secret in the existing PostgreSQL service
- Install and verify pgvector and VectorChord in the shared PostgreSQL service
- Enable pgvector, VectorChord, and earthdistance in the Immich database
- Deploy a disposable Valkey service for Immich background jobs
- Deploy the Immich machine-learning service for face detection and recognition
- Enable Intel OpenVINO acceleration through the shared i915 Kubernetes device resource
- Persist the Immich media library on its PV
- Expose Immich for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## 16. Setup ARR STACK

- Keep Sonarr, Radarr, Prowlarr, qBittorrent, and OpenVPN templates under `k0s-services/arr`
- Deploy each arr service in the `media` namespace through the media installer stage
- Give each arr service a dataset under `tank/secure/no-backup/k0s/services` with a quota and a dedicated 10Ti PV
- Keep dashboards, peer ports, and discovery protocols unpublished

### 16.1 OpenVPN gateway

- Route external traffic and DNS through OpenVPN with per-pod tun2socks helpers
- Block direct Internet fallback when the VPN fails
- Pin the OpenVPN endpoint to a literal IP and allow only its transport outside the tunnel
- Route external DNS through the VPN and cluster-local DNS through cluster DNS
- Disable guarded media IPv6 until equivalent capture and filtering exist
- Keep OpenVPN and network helpers on native console output

### 16.2 Sonarr

- Create the Sonarr dataset under `tank/secure/no-backup/k0s/services/sonarr` with a quota and a dedicated 10Ti PV
- Mount the shared media library writable
- Configure `/media/tv` as the Sonarr root folder
- Connect Sonarr to Prowlarr and qBittorrent with native API keys
- Select quality profiles during operator setup
- Keep Sonarr on native console output

### 16.3 Radarr

- Create the Radarr dataset under `tank/secure/no-backup/k0s/services/radarr` with a quota and a dedicated 10Ti PV
- Mount the shared media library writable
- Configure `/media/movies` as the Radarr root folder
- Connect Radarr to Prowlarr and qBittorrent with native API keys
- Select quality profiles during operator setup
- Keep Radarr on native console output

### 16.4 Prowlarr

- Create the Prowlarr dataset under `tank/secure/no-backup/k0s/services/prowlarr` with a quota and a dedicated 10Ti PV
- Select indexer providers during operator setup
- Connect Prowlarr to Sonarr and Radarr with native API keys
- Keep Prowlarr on native console output

### 16.5 qBittorrent

- Create the qBittorrent dataset under `tank/secure/no-backup/k0s/services/qbittorrent` with a quota and a dedicated 10Ti PV
- Mount the shared media library writable
- Bind qBittorrent to `tun0`, disable UPnP, and enable anonymous mode
- Connect qBittorrent with a Vault-managed password using the `private-cloud` WebUI username
- Enable qBittorrent file logging and forward `/config/qBittorrent/logs/qbittorrent.log` through the file-logs sidecar
- Mount qBittorrent source logs read-only in the sidecar and persist read positions on its dataset
- Start the logging sidecar before qBittorrent and stop it after the application
- Rotate qBittorrent source logs at 10MiB and remove them after seven days
- Use Recreate deployments to prevent overlapping log checkpoint writers

### 16.6 Media library

- Create the shared media-library dataset under `tank/secure/no-backup/k0s/services/media-library` with a quota and a dedicated 10Ti PV
- Mount the shared library writable in Sonarr, Radarr, and qBittorrent and read-only in Jellyfin

## 17. Setup JELLYFIN

- Keep Jellyfin templates under `k0s-services/jellyfin`
- Deploy Jellyfin in the `media` namespace through the media installer stage
- Create a Jellyfin dataset under `tank/secure/backup/k0s/services/jellyfin` with a quota and a dedicated 10Ti PV
- Mount the shared media library read-only
- Use one shared Intel i915 GPU allocation for transcoding
- Expose the configured hostname through Traefik HTTPS
- Accept connections only from Traefik and allow direct Internet metadata egress
- Apply library settings with plugin repositories disabled before Jellyfin starts
- Keep online metadata and image download enabled while disabling subtitle, plugin, and remote-media integrations
- Use native console logging without a logging sidecar
- Keep separate FFmpeg diagnostic logs on the Jellyfin dataset
- Prune closed FFmpeg diagnostics after seven days or above 1GiB while preserving active files

## 18. Setup ALLOY LOG COLLECTION

- Deploy digest-pinned Grafana Alloy 1.19.2 as one node collector in `observability`
- Create `tank/secure/no-backup/k0s/services/alloy` with a configurable 5G initial quota and a dedicated 10Ti PV/PVC
- Persist source positions and write-ahead buffers as disposable data
- Read Kubernetes CRI files through read-only host mounts and narrowly scoped discovery RBAC
- Collect workload containers, init containers, sidecars, host journal entries, and Kubernetes events
- Retain journal records for the kernel, k0s, ZFS, SSH, Zabbix Agent, and logging heartbeat
- Keep applications on native stdout/stderr wherever supported
- Use file-forwarding sidecars only for logs unavailable on stdout/stderr
- Preserve source timestamps, parse CRI framing, and join multiline exceptions
- Parse structured severity fields and known console formats, including qBittorrent's wrapped messages
- Normalize warning, error, fatal, panic, and critical levels before alert evaluation
- Preserve unclassified messages without assigning an alert level
- Index only namespace, service, container, node, job, and severity labels
- Keep request IDs, filenames, email addresses, and message text out of indexed labels
- Redact credentials, authorization headers, cookies, and mail bodies before ingestion
- Avoid duplicate collection through both container files and the Kubernetes log API
- Authenticate Alloy with OpenObserve's ingestion-only passcode
- Keep the OpenObserve administrator password out of the collector pod
- Enable Alloy's persistent write-ahead log with retry backoff and finite retries
- Keep the Alloy endpoint private with default-deny policies
- Read media logs from the node without granting media applications new egress
- Limit memory and buffering with a six-hour maximum WAL segment age
- Retry ingestion up to 120 times with one-second to 30-second backoff
- Keep source rotation independent of central retention and dataset quotas

## 19. Setup OPENOBSERVE LOG STORAGE

- Deploy one digest-pinned OpenObserve 0.90.3 node in `observability`
- Create `tank/secure/no-backup/k0s/services/openobserve` with a configurable 50G initial quota and a dedicated 10Ti PV/PVC
- Use OpenObserve local mode with disk object storage and SQLite metadata
- Retain logs for 14 days through OpenObserve compaction
- Keep OpenObserve state and log history in disposable no-backup storage
- Expose OpenObserve through an exact Traefik HTTPS hostname with authentication required
- Enforce memory limits, 10MiB ingestion payloads, and 60-second query timeouts
- Return 1,000 query rows by default and activate the memory circuit breaker at 90%
- Use native stdout/stderr logging for collection by Alloy

## 20. Observation and alerting

- Probe every workload for readiness and liveness so unhealthy containers restart or leave service
- Collect workload output, sidecar logs, host journal entries, and Kubernetes events into one store
- Parse structured severity and normalize warning, error, fatal, panic, and critical levels before evaluation
- Preserve unclassified messages as investigation evidence without assigning an alert level
- Heartbeat the log pipeline so missing collection alerts during quiet periods
- Gather host storage, hardware, and service metrics against trigger thresholds and a capacity dashboard
- Alert on storage growth, hardware health, unfixed errors, stale collectors, and overdue maintenance
- Evaluate recognized warning, error, and critical logs on a short interval
- Deduplicate and suppress repeated alerts while a problem stays open
- Email every Warning-or-higher problem, recovery, and recurring reminder through the mail service
- Confirm alert delivery at the destination inbox instead of trusting relay acceptance
- Treat missing telemetry as a failure state, not as all-clear

## 21. Setup NETWORKING

- Traefik maintains DDNS for the domain
- Stalwart maintains DDNS for smtp 
- Host ports/network is restricted. Only Traefik port is visible (http and udp for amnezia) and smtp. 
    - SSH is narrowed to local network
- Apply default-deny NetworkPolicies with explicit service flows
    - Permit application dependencies only through declared service ports and namespace selectors
- ARR stack routed through OpenVPN with fail-closed policies
    - ARR stack has no access to internet
    - In case of openVPN failure, arr stack has no connectivity (fail-switch)
- Use router forwarding for public entry and split DNS for LAN and VPN application access
- Place application services, their databases, search dependencies, and Zabbix in `private-cloud`
- Place Sonarr, Radarr, Prowlarr, qBittorrent, the OpenVPN gateway, and Jellyfin in `media`
- Place Cloudflare DDNS in `dns-system`
- Place Alloy and OpenObserve in `observability`
- Keep CNI, cluster DNS, and the GPU device plugin in `kube-system`

## 22. Setup AMNEZIAWG

- Deploy AmneziaWG in the `network-access` namespace with a configured UDP hostPort
- Install the AmneziaWG kernel module on the host
- Keep AmneziaWG routing, NAT, and peer ACLs inside its pod network namespace
- Restrict AmneziaWG peers to approved LAN destinations and public Internet forwarding
- Deny AmneziaWG peer access to other peers, pod CIDRs, service CIDRs, and media APIs
- Use native stdout/stderr logging for collection by Alloy

## 23. Setup TRAEFIK

- Deploy Traefik in the `edge` namespace with host TCP 443 for HTTPS and host TCP 25 for SMTP
- Publish application services as ClusterIP endpoints behind exact Traefik host rules
- Obtain Traefik HTTPS certificates with Cloudflare DNS-01
- Proxy SMTP TCP 25 to Stalwart without terminating STARTTLS
- Give Traefik a quota-controlled backup dataset and a dedicated 10Ti PV/PVC
- Enable structured Traefik service and access logs on stdout
- Disable the Traefik dashboard and leave unknown HTTPS hosts without a route
