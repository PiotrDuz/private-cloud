# Whole-system target specification

This file is the source of truth for the desired system state and its major decisions.
Implementation may lag behind this specification; this file does not certify deployment.

## ZFS storage

- Configure disks as RAIDZ1 in the `tank` pool
- Encrypt tank/secure with AES-256-GCM and a recoverable passphrase file
- Give tank/secure all available pool capacity without a quota or reservation
- Create tank/secure/backup and tank/secure/no-backup datasets
- Schedule monthly scrubs
- Enable auto trims
- Unlock and mount at startup through native ZFS systemd integration and ZED mount caches
- Use ashift=12, zstd compression, POSIX ACLs, xattr=sa, and atime=off

## k0s cluster

- Place container images under tank/secure/no-backup/k0s/images
- Place ephemeral kubelet data under tank/secure/no-backup/k0s/ephemeral
- Place k0s setup and configuration under tank/secure/backup/k0s/config
- Default service datasets to tank/secure/backup/k0s/services and place disposable logging data under tank/secure/no-backup/k0s/services
- Install k0s
- Start k0s after ZFS is unlocked and mounted at system startup
- Set explicit quotas for config, images, and ephemeral leaf datasets
- Keep Kubernetes manifests as Jinja templates under k0s-services and render them directly with Ansible
- Load the Intel i915 driver and install the matching firmware for integrated graphics
- Deploy the Intel Kubernetes GPU plugin with shared allocations for machine learning and media workloads
- Run one combined controller and worker with kube-router networking
- Pin the k0s version and checksum in the owning role
- Use node-bound local storage and single-writer workloads on this single-host cluster
- Store container logs under /tank/secure/k0s/kubelet/logs in the quota-controlled ephemeral kubelet dataset
- Rotate container logs as five 10Mi files per container
- Bound the persistent host journal to 1GiB and seven days initially
- Keep CPU requests and memory limits without CPU limits for all Kubernetes containers

## PostgreSQL

- Create postgres zfs dataset under tank/secure/backup/k0s/services/postgres
- Tune ZFS and PostgreSQL using only the selected settings from the [tuning reference](https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers)
    * ZFS settings
        + Set recordsize=8k, enable compression, and reduce read-ahead
        + Use primarycache=all because container RAM limits are aggressive
        + Use logbias=latency
    * PostgreSQL settings
        + Set shared_buffers to 25% of the user-provided maximum container memory
        + Set full_page_writes=off and disable checksumming and compression
        + Tune wal_init_zero and wal_recycle
- Postgres service with its own Kubernetes volume linked with dataset is deployed in k0s
- Use the TensorChord PostgreSQL 18 image and verify pgvector and VectorChord
- Disable the file collector and send PostgreSQL logs to stderr with an explicit timestamp and process prefix

## Meilisearch

- Create a Meilisearch dataset under tank/secure/backup/k0s/services/meilisearch with a quota
- Deploy Meilisearch in k0s with its own 10Ti PV
- Enable native JSON stderr logging for collection by Alloy

## Stalwart email

- Deploy Stalwart with its own dataset under tank/secure/backup/k0s/services/stalwart, 10Ti PV, and quota
- Create a Stalwart database, login role, and credentials Secret in the existing postgres service
- Configure the data store to use the Stalwart postgres database
- Configure the blob store as filesystem storage on the Stalwart PV
- Configure the search store to use Meilisearch
- Configure the Default in-memory store to use the postgres data store
- Configure Stalwart as the mailbox and JMAP submission service for the user-provided domain
- Publish JMAP, web access, and management through Traefik HTTPS TCP 443
- Accept forwarded inbound mail through Traefik SMTP TCP 25 with Proxy Protocol v2
- Terminate SMTP STARTTLS in Stalwart with an automatically renewed certificate
- Use Let's Encrypt DNS-01 and a dedicated Cloudflare token for the Stalwart certificate
- Keep IMAPS 993 and submission ports 465 and 587 unexposed
- Map forwarding-subdomain recipients to primary-domain Stalwart accounts
- Configure the inbox.eu SMTP relay
    * Deliver local-domain mail locally and route other outbound mail through inbox.eu
    * Use the configured relay hostname, port, username, and implicit TLS or STARTTLS mode
    * Reject invalid relay certificates
    * Supply the relay password through the Stalwart runtime Secret
    * Use the same relay settings for Zabbix and OpenObserve notification delivery
    * Use the configured notification sender address for alert emails
    * Address alerts to `<stalwart.mailbox_username>@<stalwart.forwarding_domain>`
    * Route alert delivery through the forwarding-domain MX and Traefik TCP 25 to Stalwart
    * Deliver the forwarding alias into `<stalwart.mailbox_username>@<stalwart.domain>`
    * Restrict notification SMTP egress to the relay IPv4 addresses resolved when policies are applied
- Support JMAP access, SMTP forwarding, filtering, outbound relay, and automatic certificate renewal
- Use native stdout/stderr logging for collection by Alloy

## Apache Tika

- Create an Apache Tika dataset under tank/secure/backup/k0s/services/tika with a quota
- Deploy Apache Tika in k0s with its own 10Ti PV
- Use native stdout/stderr logging for collection by Alloy

## Bleve

- Create a Bleve dataset under tank/secure/backup/k0s/services/bleve with a quota
- Create a dedicated 10Ti PV for the embedded OpenCloud Bleve search backend
- Collect embedded Bleve search logs through the OpenCloud container

## OnlyOffice

- Create an OnlyOffice dataset under tank/secure/backup/k0s/services/onlyoffice with a quota
- Deploy OnlyOffice Community Edition in k0s with its own 10Ti PV
- Enable the OnlyOffice WOPI integration
- Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
- Use OnlyOffice 9.4.0.1's native entrypoint to forward /var/log/onlyoffice to container output without a logging sidecar
- Persist source logs on the OnlyOffice dataset
- Check source rotation every 15 minutes with a 10MiB limit and seven-day retention
- Run container root inside a Kubernetes user namespace

## OpenCloud

- Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
- Configure OpenCloud to use Apache Tika for content extraction
- Configure the search service to use the Bleve backend
- Configure supported cache stores to use in-memory storage
- Configure the file storage to use filesystem storage on the OpenCloud PV
- Enable the built-in collaboration service and connect it to OnlyOffice
- Install and configure the Draw.io web extension
- Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy

## Grist

- Deploy Grist with its own dataset under tank/secure/backup/k0s/services/grist, 10Ti PV, and quota
- Create a Grist database, login role, and credentials Secret in the existing postgres service
- Persist Grist documents on its PV and isolate formulas with Pyodide
- Expose Grist for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy

## Manticore Search

- Create a Manticore Search dataset under tank/secure/backup/k0s/services/manticore with a quota
- Deploy Manticore Search in k0s with its own 10Ti PV
- Use native stdout/stderr logging for collection by Alloy

## Redis for AFFiNE

- Deploy `redis-affine` as an independent k0s service for AFFiNE
- Keep Redis data ephemeral without a dataset, PV, or PVC
- Restrict Redis ingress to the AFFiNE server and database preparation Job
- Use native stdout/stderr logging for collection by Alloy

## AFFiNE

- Deploy AFFiNE with its own dataset under tank/secure/backup/k0s/services/affine, 10Ti PV, and quota
- Create an AFFiNE database with pgvector enabled in the shared PostgreSQL service
- Configure the server-side indexer to use Manticore Search
- Use the independent `redis-affine` service
- Prepare the fresh AFFiNE database schema before the server starts
- Persist AFFiNE blobs and configuration on its PV
- Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## Valkey for Immich

- Deploy `valkey-immich` as an independent k0s service for Immich
- Keep Valkey data ephemeral without a dataset, PV, or PVC
- Restrict Valkey ingress to the Immich server
- Use native stdout/stderr logging for collection by Alloy

## Immich

- Deploy Immich with its own dataset under tank/secure/backup/k0s/services/immich, 10Ti PV, and quota
- Create an Immich database, login role, and credentials Secret in the existing PostgreSQL service
- Install and verify pgvector and VectorChord in the shared PostgreSQL service
- Enable pgvector, VectorChord, and earthdistance in the Immich database
- Deploy a disposable Valkey service for Immich background jobs
- Deploy the Immich machine-learning service for face detection and recognition
- Enable Intel OpenVINO acceleration through the shared i915 Kubernetes device resource
- Persist the Immich media library on its PV
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## ARR stack

- Keep Sonarr, Radarr, Prowlarr, qBittorrent, and OpenVPN templates under k0s-services/arr
- Deploy the arr stack in the media namespace through the media installer stage
- Give each ARR service a dataset under tank/secure/no-backup/k0s/services with a quota and a dedicated 10Ti PV
- Create the shared media-library dataset under tank/secure/no-backup/k0s/services/media-library with a quota and a dedicated 10Ti PV
- Mount the shared library writable in Sonarr, Radarr, and qBittorrent
- Route external traffic and DNS through OpenVPN with per-pod tun2socks helpers
- Block direct Internet fallback when the VPN fails
- Keep dashboards, peer ports, and discovery protocols unpublished
- Bind qBittorrent to tun0, disable UPnP, and enable anonymous mode
- Connect Prowlarr, Sonarr, Radarr, and qBittorrent automatically with native API keys and a Vault-managed qBittorrent password
- Keep Sonarr, Radarr, Prowlarr, OpenVPN, and network helpers on native console output
- Enable qBittorrent file logging and forward /config/qBittorrent/logs/qbittorrent.log through the file-logs sidecar
- Mount qBittorrent source logs read-only in the sidecar and persist read positions on its dataset
- Start the logging sidecar before qBittorrent and stop it after the application
- Rotate qBittorrent source logs at 10MiB and remove them after seven days
- Use Recreate deployments to prevent overlapping log checkpoint writers
- Pin the OpenVPN endpoint to a literal IP and allow only its transport outside the tunnel
- Route external DNS through the VPN and cluster-local DNS through cluster DNS
- Disable guarded media IPv6 until equivalent capture and filtering exist
- Configure /media/tv and /media/movies as ARR root folders
- Collect separate 720p, 1080p, or 2160p preferences for Sonarr and Radarr during initial configuration
- Create or update a `private-cloud` quality profile in each application during installation
- Allow standard HDTV, WEB, and Blu-ray qualities from 720p through the selected resolution
- Exclude remux, raw, disc, and low-quality theatrical sources
- Use Blu-ray at the selected resolution as the automatic upgrade cutoff
- Select the `private-cloud` profile when adding series or movies and configuring import lists
- Select indexer providers and credentials during operator setup
- Create Sonarr, Radarr, Prowlarr, and qBittorrent datasets under tank/secure/no-backup/k0s/services/<service>
- Use the `private-cloud` WebUI username with the Vault-managed qBittorrent password
- Mount the shared media library read-only in Jellyfin

## Jellyfin

- Keep Jellyfin templates under k0s-services/jellyfin
- Deploy Jellyfin in the media namespace through the media installer stage
- Create a Jellyfin dataset under tank/secure/backup/k0s/services/jellyfin with a quota and a dedicated 10Ti PV
- Mount the shared media library read-only
- Use one shared Intel i915 GPU allocation for transcoding
- Expose the configured hostname through Traefik HTTPS
- Accept connections only from Traefik and allow direct Internet metadata egress
- Apply library settings with plugin repositories disabled before Jellyfin starts
- Keep online metadata and image download enabled while disabling subtitle, plugin, and remote-media integrations
- Use native console logging without a logging sidecar
- Keep separate FFmpeg diagnostic logs on the Jellyfin dataset
- Prune closed FFmpeg diagnostics after seven days or above 1GiB while preserving active files

## Security

- Run ordinary application containers with fixed non-root UIDs and disabled privilege escalation
    * Run AFFiNE, Immich server, and OnlyOffice container root inside Kubernetes user namespaces
    * Map user-namespaced root to an unprivileged host UID
    * Preserve the container startup capabilities required by AFFiNE and OnlyOffice inside their user namespaces
- Drop Linux capabilities except for workload-specific startup and networking requirements
- Retain NET_RAW for Zabbix ICMP checks and NET_BIND_SERVICE for services binding privileged ports
- Reserve host access and network administration for networking, GPU support, and log collection workloads
- Run Alloy with root read access to host logs through read-only mounts and with all capabilities dropped
- Align persistent dataset ownership with each workload's UID and GID
- Disable service-account token automounting for applications that do not need Kubernetes API access
    * Limit Alloy Kubernetes API access to workload discovery and event collection
- Enforce namespace default-deny policies with explicit service and port exceptions
- Keep application credentials in role-owned Kubernetes Secrets and persistent plaintext secrets out of the repository
- Keep ingestion credentials separate from OpenObserve administrator credentials
- Keep media VPN isolation independent of log collection

## Networking

### Public entry and DNS

- Deploy Traefik with host TCP 443 for HTTPS and host TCP 25 for SMTP
- Publish application services as ClusterIP endpoints behind exact Traefik host rules
- Obtain Traefik HTTPS certificates with Cloudflare DNS-01
- Proxy SMTP TCP 25 to Stalwart without terminating STARTTLS
- Maintain configured public A records with a dedicated Cloudflare DDNS token
- Use router forwarding for public entry and split DNS for LAN and VPN application access
- Use split DNS and the internal Traefik address for OpenCloud and OnlyOffice callbacks
- Give Traefik a quota-controlled backup dataset and a dedicated 10Ti PV/PVC
- Enable structured Traefik service and access logs on stdout
- Disable the Traefik dashboard and leave unknown HTTPS hosts without a route
- Keep DDNS credentials separate from Traefik and Stalwart certificate credentials

### Host access and service isolation

- Restrict SSH, the Kubernetes API, and Zabbix TCP 31051 to local networks
- Permit only TCP 443, TCP 25, and the AmneziaWG UDP port from untrusted networks
- Block obsolete application NodePorts and undeclared host ports
- Label managed namespaces and enforce default-deny ingress and egress with explicit exceptions
- Permit application dependencies only through declared service ports and namespace selectors
- Maintain the permitted connection matrix in [NETWORKING.md](docs/NETWORKING.md)

### Namespace and host placement

- Place application services, their databases, search dependencies, and Zabbix in private-cloud
- Place Sonarr, Radarr, Prowlarr, qBittorrent, the OpenVPN gateway, and Jellyfin in media
- Place Traefik in edge, AmneziaWG in network-access, and Cloudflare DDNS in dns-system
- Place Alloy and OpenObserve in observability
- Keep CNI, cluster DNS, and the GPU device plugin in kube-system
- Keep ZFS, the host firewall, Zabbix Agent, and journal collection support on the host

### VPN and media routing

- Install the AmneziaWG kernel module on the host
- Keep AmneziaWG routing, NAT, and peer ACLs inside its pod network namespace
- Route guarded media application egress through OpenVPN with fail-closed policies
- Keep Jellyfin ingress behind Traefik and allow direct Internet metadata egress
- Restrict AmneziaWG peers to approved LAN destinations and public Internet forwarding
- Deny AmneziaWG peer access to other peers, pod CIDRs, service CIDRs, and media APIs

### AmneziaWG

- Deploy AmneziaWG in the network-access namespace with a configured UDP hostPort
- Use native stdout/stderr logging for collection by Alloy

## Observability

### System-wide requirements

- Probe every workload for readiness and liveness so unhealthy containers restart or leave service
- Keep infrastructure metric alerts in Zabbix and recognized log alerts in OpenObserve
- Preserve unclassified messages as investigation evidence without assigning an alert level
- Deduplicate and suppress repeated alerts while a problem stays open
- Email every Warning-or-higher problem, recovery, and recurring reminder through the mail service
- Confirm alert delivery at the destination inbox instead of trusting relay acceptance
- Treat missing telemetry as a failure state, not as all-clear

### Zabbix metrics and alerts

- Run the Zabbix metrics gatherer on the host at system startup
    * ZFS errors
    * Scrub runs
    * Fixed leaf dataset size, quota, and quota utilization
    * Total pool size
    * SMART disk metrics
    * System RAM and CPU performance
    * RAM ECC corrected and uncorrected errors
    * Old snapshots, large snapshots
- Deploy Zabbix server with its own dataset, quota, and 10Ti PV in the cluster
- Zabbix service creates its database, login role, and credentials Secret
- Connect Zabbix to its database
- Expose the Zabbix server port to the host metrics gatherer
- Alert thresholds
    * Warn when tank usage exceeds 80% and raise a high alert above 90%
    * Warn on service dataset quota utilization at 80% and raise high alerts for fixed leaf datasets at 90%
    * Alert on SMART disk low health
    * Alert on unfixed ZFS error
    * Warn on ZFS error that has been fixed (scrub or normal operation)
    * Alert on unfixed ECC error
    * Warn on ECC error that has been fixed
- Link active Linux, SMART, ZFS, and ECC templates to private-cloud-zabbix
- Maintain the Dataset capacity dashboard from the enabled dataset catalog
- Alert on stale collectors, old snapshots, overdue scrubs, and unavailable ECC telemetry
- Email Warning, Average, High, and Disaster problems through the configured relay when notifications are enabled
- Use native stdout/stderr for Zabbix containers
- Route Zabbix Agent and host collector diagnostics through system logging, the journal, and Alloy into OpenObserve
- Keep ZFS, ECC, and SMART metric results in Zabbix while forwarding collector failures as logs
- Send Zabbix problem, recovery, and hourly reminder emails to the local Stalwart mailbox
- Retry Zabbix email delivery up to ten times at one-minute intervals
- Pause Zabbix notifications for suppressed problems during maintenance
- Check enabled HTTPS and Stalwart SMTP STARTTLS certificates through Zabbix with expiry alerts at 21 and 7 days
- Keep Alloy health, retry, and dropped-entry monitoring in Zabbix
- Run the Zabbix Alloy and certificate collector without sudo or OpenObserve administrator credentials

### Alloy log collection

- Deploy digest-pinned Grafana Alloy as one node collector in observability
- Create tank/secure/no-backup/k0s/services/alloy with a configurable 5G initial quota and dedicated 10Ti PV/PVC
- Collect workload containers, init containers, sidecars, host journal entries, and Kubernetes events
    * Retain journal records for the kernel, k0s, ZFS, SSH, Zabbix Agent, and logging heartbeat
    * Collect host collector errors identified by private-cloud-zabbix-* syslog names
- Keep applications on native stdout/stderr wherever supported
    * Use file-forwarding sidecars only for logs unavailable on stdout/stderr
- Normalize warning, error, fatal, panic, and critical levels before alert evaluation
- Index only namespace, service, container, node, job, and severity labels
- Avoid duplicate collection through both container files and the Kubernetes log API
- Authenticate Alloy with OpenObserve's ingestion-only passcode
- Enable Alloy's persistent write-ahead log with retry backoff and finite retries
    * Limit memory and buffering with a six-hour maximum WAL segment age
    * Keep source rotation independent of central retention and dataset quotas
- Keep the Alloy endpoint private with default-deny policies
- Read media logs from the node without granting media applications new egress

### OpenObserve storage and queries

- Deploy one digest-pinned OpenObserve 0.90.3 node in observability
- Create tank/secure/no-backup/k0s/services/openobserve with a configurable 50G initial quota and dedicated 10Ti PV/PVC
- Use OpenObserve local mode with disk object storage and SQLite metadata
- Retain logs for 14 days through OpenObserve compaction
- Return 1,000 query rows by default and activate the memory circuit breaker at 90%
- Use native stdout/stderr logging for collection by Alloy

### Log alerts and delivery

- Provision three severity rules and one missing-heartbeat rule in the logs stream
- Evaluate each rule every minute over the preceding five minutes
- Trigger severity alerts on at least one warn, error, or critical entry without an additional pending period
- Include Kubernetes Warning events and classify Traefik HTTP 5xx responses as errors
- Suppress repeated notifications from each rule for five minutes
- Keep OpenObserve internal logs searchable while excluding them from severity alerts to prevent notification feedback loops
- Emit a host logging heartbeat to detect missing collection during quiet periods
- Trigger the missing-heartbeat rule when no host logging heartbeat appears in the five-minute window
- Disable OpenObserve SMTP and all four managed rules when notifications are disabled
- Include the alert name, matching row count, severity, namespace, service, message, and investigation link in log emails
- Keep log alert delivery dependent on OpenObserve, the external relay, DNS, inbound SMTP, and the local mailbox services

### Monitoring boundaries

- Keep OpenObserve health, metrics, internal warnings, and heartbeat searches outside Zabbix application probes
- Keep shared dataset capacity and edge certificate monitoring separate from OpenObserve application health probes
