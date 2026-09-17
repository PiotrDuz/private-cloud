# Whole-system target specification

This file is the source of truth for the desired system state and its major decisions.

## Table of contents

- [ZFS storage](#zfs-storage)
- [k0s cluster](#k0s-cluster)
- [PostgreSQL](#postgresql)
- [Keycloak](#keycloak)
- [Meilisearch](#meilisearch)
- [Stalwart email](#stalwart-email)
- [Apache Tika](#apache-tika)
- [Bleve](#bleve)
- [OnlyOffice](#onlyoffice)
- [OpenCloud](#opencloud)
- [Grist](#grist)
- [Manticore Search](#manticore-search)
- [Redis for AFFiNE](#redis-for-affine)
- [AFFiNE](#affine)
- [Valkey for Immich](#valkey-for-immich)
- [Immich](#immich)
- [ARR stack](#arr-stack)
    * [Sonarr](#sonarr)
    * [Radarr](#radarr)
    * [Prowlarr](#prowlarr)
    * [qBittorrent](#qbittorrent)
    * [OpenVPN](#openvpn)
- [Jellyfin](#jellyfin)
- [Security](#security)
- [Networking](#networking)
    * [Public entry and DNS](#public-entry-and-dns)
    * [Traefik](#traefik)
    * [Host access and service isolation](#host-access-and-service-isolation)
    * [Namespace and host placement](#namespace-and-host-placement)
    * [VPN and media routing](#vpn-and-media-routing)
    * [AmneziaWG](#amneziawg)
- [Observability](#observability)
    * [System-wide requirements](#system-wide-requirements)
    * [Zabbix metrics and alerts](#zabbix-metrics-and-alerts)
        + [Zabbix host](#zabbix-host)
        + [Zabbix k0s service](#zabbix-k0s-service)
    * [Alloy log collection](#alloy-log-collection)
    * [OpenObserve](#openobserve)
        + [Storage and queries](#storage-and-queries)
        + [Log alert rules and delivery](#log-alert-rules-and-delivery)

## ZFS storage

- Configure disks as RAIDZ1 in the `tank` pool
- Encrypt tank/secure with AES-256-GCM and a recoverable passphrase file
- Give tank/secure all available pool capacity without a quota or reservation
- Create tank/secure/backup and tank/secure/no-backup datasets
- Schedule monthly scrubs
- Enable auto trims
- Unlock and mount at startup through native ZFS systemd integration and ZED list cache
- Use ashift=12, zstd compression, POSIX ACLs, xattr=sa, and atime=off

## k0s cluster

- Place container images under tank/secure/no-backup/k0s/images
- Place ephemeral kubelet data under tank/secure/no-backup/k0s/ephemeral
- Place k0s setup and configuration under tank/secure/backup/k0s/config
- Default service datasets to tank/secure/backup/k0s/services and place disposable logging data under tank/secure/no-backup/k0s/services
- Install k0s
- Start k0s after ZFS is unlocked and mounted at system startup
- Set explicit quotas for config, images, and ephemeral leaf datasets
- Keep public workload manifests as Jinja templates under k0s-services and render them directly with Ansible
- Keep role-owned Secret and Namespace manifests in role templates
- Load the Intel i915 driver and install the matching firmware for integrated graphics
- Deploy the Intel Kubernetes GPU plugin with shared allocations for machine learning and media workloads
- Run one combined controller and worker with kube-router networking
- Pin the k0s version and checksum in the owning role
- Use node-bound local storage and one replica per workload on this single-host cluster
- Store container logs under /tank/secure/k0s/kubelet/logs in the quota-controlled ephemeral kubelet dataset
- Rotate container logs as five 10Mi files per container
- Bound the persistent host journal to 1GiB and seven days when the logging stage is enabled
- Keep CPU requests and memory limits without CPU limits for all repository-managed containers

## PostgreSQL

- Create postgres zfs dataset under tank/secure/backup/k0s/services/postgres
- Tune ZFS and PostgreSQL using only the selected settings from the [tuning reference](https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers)
    * ZFS settings
        + Set recordsize=8k, enable compression, and reduce read-ahead
        + Use primarycache=all because container RAM limits are aggressive
        + Use logbias=latency
    * PostgreSQL settings
        + Set shared_buffers to 25% of the user-provided maximum container memory
        + Set full_page_writes=off, data_checksums=off, and wal_compression=off
        + Set wal_init_zero=off and wal_recycle=off
- Postgres service with its own Kubernetes volume linked with dataset is deployed in k0s
- Use the TensorChord PostgreSQL 18 image with pgvector and VectorChord
- Disable the file collector and send PostgreSQL logs to stderr with an explicit timestamp and process prefix

## Keycloak

- Deploy Keycloak in the private-cloud namespace as the shared OpenID Connect (OIDC) identity provider
- Create tank/secure/backup/k0s/services/keycloak with a quota and a dedicated 10Ti PV/PVC
- Create a dedicated Keycloak database, login role, and credentials Secret in the shared PostgreSQL service
- Persist identity, realm, and client configuration in the backed-up PostgreSQL database
- Expose Keycloak at a configured hostname through Traefik HTTPS
- Use one shared realm with separate OIDC clients for each application and its supported web, desktop, and mobile clients
- Store confidential-client secrets in role-owned Kubernetes Secrets and keep public clients secret-free
- Restrict redirect URIs and web origins to each application's documented browser and native-client callbacks
- Use one stable HTTPS realm issuer reachable by browsers and pods through split DNS
- Configure Keycloak's [public hostname and trusted proxy headers](https://www.keycloak.org/server/reverseproxy) for Traefik TLS termination
- Keep Keycloak administration restricted to designated administrators
- End local application sessions on logout and use provider logout where supported
- Use Keycloak login for every user-facing service except AmneziaWG, the ARR stack, Zabbix, and OpenObserve
    * Include Stalwart web access and management, OpenCloud, Grist, AFFiNE, Immich, and Jellyfin
    * Use native OIDC or an integration that establishes the application's authenticated user session
    * Keep backend APIs, database connections, mail transport, and log ingestion on their service credentials
    * Keep internal services without interactive logins private
- Use native stdout/stderr logging for collection by Alloy

## Meilisearch

- Create a Meilisearch dataset under tank/secure/backup/k0s/services/meilisearch with a quota
- Deploy Meilisearch in k0s with its own 10Ti PV
- Enable native JSON stderr logging for collection by Alloy

## Stalwart email

- Deploy Stalwart with its own dataset under tank/secure/backup/k0s/services/stalwart, 10Ti PV, and quota
- Create a Stalwart database, login role, and credentials Secret in the shared PostgreSQL service
- Configure the data store to use the Stalwart postgres database
- Configure the blob store as filesystem storage on the Stalwart PV
- Configure the search store to use Meilisearch
- Configure the Default in-memory store to use the postgres data store
- Configure Stalwart as the mailbox and JMAP submission service for the user-provided domain
- Use the Keycloak-backed OIDC directory for user authentication and retain Stalwart mailbox and administrator permissions
    * Require OIDC-capable web and JMAP clients to obtain Keycloak access tokens
    * Validate the Stalwart token audience and map identity claims to primary-domain mailboxes
    * Pre-create mailboxes and forwarding aliases through the management API or CLI before first login
    * Manage mailbox suspension and deletion explicitly without relying on OIDC or Enterprise SCIM
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
- Authenticate document users through the Keycloak-authenticated OpenCloud session and its WOPI access tokens
- Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
- Use OnlyOffice 9.4.0.1's native entrypoint to forward /var/log/onlyoffice to container output without a logging sidecar
- Persist source logs on the OnlyOffice dataset
- Check source rotation every 15 minutes with a 10MiB limit and seven-day retention
- Run container root inside a Kubernetes user namespace

## OpenCloud

- Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
- Authenticate OpenCloud web, desktop, and mobile clients through Keycloak OIDC with authorization code flow and PKCE
- Use OpenCloud autoprovisioning mode with Keycloak as the identity source and OpenCloud's internal user directory
- Register public PKCE clients for OpenCloud web, desktop, Android, and iOS with matching WebFinger configuration
- Map Keycloak claims to stable OpenCloud user identities and explicit user or administrator roles
- Configure OpenCloud to use Apache Tika for content extraction
- Configure the search service to use the Bleve backend
- Configure supported cache stores to use in-memory storage
- Configure the file storage to use filesystem storage on the OpenCloud PV
- Enable the built-in collaboration service and connect it to OnlyOffice
- Install and configure the Draw.io web extension within authenticated OpenCloud sessions
- Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy

## Grist

- Deploy Grist with its own dataset under tank/secure/backup/k0s/services/grist, 10Ti PV, and quota
- Create a Grist database, login role, and credentials Secret in the shared PostgreSQL service
- Persist Grist documents on its PV and isolate formulas with Pyodide
- Use [Grist forwarded-header authentication](https://support.getgrist.com/install/forwarded-headers/) through Traefik and a Keycloak OIDC ForwardAuth helper
    * Set `GRIST_FORWARD_AUTH_HEADER=X-Forwarded-User` to receive the authenticated user's email
    * Route Grist `/auth/login`, the OIDC callback, and configured logout path through the authentication helper
- Use verified Keycloak email identities for Grist accounts and keep document permissions in Grist
- Use a single Grist team site for the supported forwarded-header login flow
- Accept Grist user-facing traffic only from Traefik and discard client-supplied identity headers
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
- Configure [AFFiNE OIDC sign-in](https://affine.pro/enterprise) with Keycloak through its administration settings
    * Keep the self-hosted OIDC sign-in licence-free within ten seats
- Configure its confidential client, issuer, verified email claims, and HTTPS `/oauth/callback` redirect
- Permit AFFiNE's OIDC client to reach only the trusted Keycloak issuer when it resolves to a private address
- Configure the server-side indexer to use Manticore Search
- Use the independent `redis-affine` service
- Prepare the fresh AFFiNE database schema before the server starts
- Persist AFFiNE blobs and configuration on its PV
- Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## Valkey for Immich

- Deploy `valkey-immich` through the Immich installer stage
- Keep Valkey data ephemeral without a dataset, PV, or PVC
- Restrict Valkey ingress to the Immich server
- Use native stdout/stderr logging for collection by Alloy

## Immich

- Deploy Immich with its own dataset under tank/secure/backup/k0s/services/immich, 10Ti PV, and quota
- Create an Immich database, login role, and credentials Secret in the shared PostgreSQL service
- Provide pgvector and VectorChord in the shared PostgreSQL service
- Enable pgvector, VectorChord, and earthdistance in the Immich database
- Deploy a disposable Valkey service for Immich background jobs
- Deploy the Immich machine-learning service for face detection and recognition
- Enable Intel OpenVINO acceleration through the shared i915 Kubernetes device resource
- Persist the Immich media library on its PV
- Enable [Immich native OIDC](https://docs.immich.app/administration/oauth/) with Keycloak for web and mobile clients
- Register a confidential client with HTTPS `/auth/login`, `/user-settings`, and `app.immich:///oauth-callback` redirects
- Map approved users to Immich accounts and manage administrator grants explicitly
- Configure Immich backchannel logout and manage account permissions within Immich
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## ARR stack

- Keep Sonarr, Radarr, Prowlarr, qBittorrent, and OpenVPN templates under k0s-services/arr
- Deploy the ARR stack in the media namespace through the media installer stage
- Give Sonarr, Radarr, Prowlarr, and qBittorrent a dataset under tank/secure/no-backup/k0s/services/<service> with a quota and a dedicated 10Ti PV
- Keep the OpenVPN gateway stateless without a dataset
- Create the shared media-library dataset under tank/secure/no-backup/k0s/services/media-library with a quota and a dedicated 10Ti PV
- Keep dashboards, peer ports, and discovery protocols unpublished
- Connect Prowlarr, Sonarr, Radarr, and qBittorrent automatically with native API keys and a Vault-managed qBittorrent password
- Keep Sonarr, Radarr, Prowlarr, OpenVPN, and network helpers on native console output
- Use a Recreate deployment for qBittorrent to prevent overlapping log checkpoint writers
- Apply the shared quality policy to Sonarr and Radarr
    * Create or update a `private-cloud` quality profile in each application during installation
    * Allow standard HDTV, WEB, and Blu-ray qualities from 720p through the selected resolution
    * Exclude remux, raw, disc, and low-quality theatrical sources
    * Use Blu-ray at the selected resolution as the automatic upgrade cutoff
    * Select the `private-cloud` profile when adding series or movies and configuring import lists

### Sonarr

- Mount the shared media library writable
- Configure `/media/tv` as the root folder
- Collect a separate 720p, 1080p, or 2160p preference during initial configuration

### Radarr

- Mount the shared media library writable
- Configure `/media/movies` as the root folder
- Collect a separate 720p, 1080p, or 2160p preference during initial configuration

### Prowlarr

- Select indexer providers and credentials during operator setup

### qBittorrent

- Mount the shared media library writable
- Bind qBittorrent to tun0, disable UPnP, and enable anonymous mode
- Use the `private-cloud` WebUI username with the Vault-managed qBittorrent password
- Enable file logging and forward /config/qBittorrent/logs/qbittorrent.log through the file-logs sidecar
- Mount source logs read-only in the sidecar and persist read positions on the qBittorrent dataset
- Start the logging sidecar before qBittorrent and stop it after the application
- Rotate source logs at 10MiB and remove them after seven days

### OpenVPN

- Route guarded media external traffic and DNS through OpenVPN with per-pod tun2socks helpers
- Block direct Internet fallback when the VPN fails
- Pin the OpenVPN endpoint to a literal IP and allow only its transport outside the tunnel
- Route external DNS through the VPN and cluster-local DNS through cluster DNS
- Disable guarded media IPv6 through the IPv4-only cluster configuration until equivalent capture and filtering exist

## Jellyfin

- Keep Jellyfin templates under k0s-services/jellyfin
- Deploy Jellyfin in the media namespace through the media installer stage
- Create a Jellyfin dataset under tank/secure/backup/k0s/services/jellyfin with a quota and a dedicated 10Ti PV
- Mount the shared media library read-only
- Use one shared Intel i915 GPU allocation for transcoding
- Expose the configured hostname through Traefik HTTPS
- Accept connections only from Traefik and allow direct Internet metadata egress
- Enable Keycloak OIDC login through a pinned [Jellyfin OIDC plugin](https://github.com/aussierk/jellyfin-plugin-oidc) compatible with the deployed Jellyfin version
- Map Keycloak application roles to Jellyfin users, library access, and administrator permissions
- Support native Jellyfin clients through [OIDC-authorized Quick Connect](https://github.com/aussierk/jellyfin-plugin-oidc#mobile--native-apps-quick-connect) where the client supports it
- Apply library settings and install only the approved SSO plugin before Jellyfin starts
- Keep online metadata and image download enabled while disabling subtitle, unrelated plugin, and remote-media integrations
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
- Use Keycloak as the shared identity source for OIDC-enabled applications while retaining application-specific authorization
- Keep host and Kubernetes administration on their own credentials and workload identities
- Keep ingestion credentials separate from OpenObserve administrator credentials
- Keep media VPN isolation independent of log collection

## Networking

### Public entry and DNS

- Maintain configured public A records with a dedicated Cloudflare DDNS token

### Traefik

- Deploy Traefik with host TCP 443 for HTTPS and host TCP 25 for SMTP
- Publish application services as ClusterIP endpoints behind exact Traefik host rules
- Obtain Traefik HTTPS certificates with Cloudflare DNS-01
- Proxy SMTP TCP 25 to Stalwart without terminating STARTTLS
- Give Traefik a quota-controlled backup dataset and a dedicated 10Ti PV/PVC
- Enable structured Traefik service and access logs on stdout
- Disable the Traefik dashboard and leave unknown HTTPS hosts without a route
- Run a stateless [traefik-forward-auth](https://github.com/thomseddon/traefik-forward-auth) helper in edge for Grist's Keycloak OIDC login
- Keep the helper's OIDC client secret and cookie-signing secret in Kubernetes Secrets
- Configure ForwardAuth to pass the authenticated email to Grist through `X-Forwarded-User`
- Strip incoming identity headers before authentication and forward only the helper's verified identity
- Give the helper a dedicated confidential Keycloak client and restrict access to approved email identities
- Handle Grist login, OIDC callbacks, and logout without an authentication redirect loop
- Preserve native application authentication for OIDC APIs, mail protocols, and WOPI callbacks

### Host access and service isolation

- Restrict SSH, the Kubernetes API, and Zabbix TCP 31051 to local networks
- Permit only TCP 443, TCP 25, the AmneziaWG UDP port, ICMP, and DHCP from untrusted networks
- Block obsolete application NodePorts and undeclared host ports
- Label managed namespaces and enforce default-deny ingress and egress with explicit exceptions
- Permit application dependencies only through declared service ports and namespace selectors
- Permit OIDC-enabled services and the edge ForwardAuth helper to reach Keycloak for discovery, token exchange, user information, and signing keys
- Permit configured Keycloak backchannel logout calls to applications that support them

### Namespace and host placement

- Place application services, Keycloak, their databases, search dependencies, and Zabbix in private-cloud
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
- Authenticate VPN peers using their configured keys
- Use native stdout/stderr logging for collection by Alloy

## Observability

### System-wide requirements

- Probe every workload container for readiness and liveness so unhealthy containers restart or leave service
    * Exempt init containers, Jobs, CronJobs, and host device plugins
- Preserve unclassified messages as investigation evidence without assigning an alert level
- Deduplicate and suppress repeated alerts while a problem stays open
- Email every Warning-or-higher problem, recovery, and recurring reminder through the mail service
- Confirm alert delivery at the destination inbox instead of trusting relay acceptance
- Treat missing telemetry as a failure state, not as all-clear

### Zabbix metrics and alerts

- Keep infrastructure metrics and metric alerts in Zabbix
- Keep ZFS, ECC, and SMART metric results in Zabbix while forwarding collector failures as logs
- Check enabled HTTPS and Stalwart SMTP STARTTLS certificates through Zabbix with expiry alerts at 21 and 7 days
- Keep Alloy health, retry, and dropped-entry monitoring in Zabbix
- Run the Zabbix Alloy and certificate collector without sudo or OpenObserve administrator credentials

#### Zabbix host

- Run the Zabbix metrics gatherer on the host at system startup
    * ZFS errors
    * Scrub runs
    * Fixed leaf dataset quota, quota headroom, and quota utilization
    * Total pool size
    * SMART disk metrics
    * System RAM and CPU performance
    * RAM ECC corrected and uncorrected errors
    * Old snapshots, large snapshots
- Route Zabbix Agent and host collector diagnostics through system logging, the journal, and Alloy into OpenObserve

#### Zabbix k0s service

- Deploy Zabbix server with its own dataset, quota, and 10Ti PV in the cluster
- Zabbix service creates its database, login role, and credentials Secret
- Connect Zabbix to its database
- Use local username/password login over HTTPS for the Zabbix web interface without Keycloak OIDC
- Expose the Zabbix server port to the host metrics gatherer
- Alert thresholds
    * Warn when tank usage exceeds 80% and raise a high alert above 90%
    * Warn on service dataset quota utilization at 80% and raise high alerts for fixed leaf datasets at 90%
    * Alert on SMART disk low health through the linked stock SMART template
    * Alert on unfixed ZFS error
    * Warn on ZFS error that has been fixed (scrub or normal operation)
    * Alert on unfixed ECC error
    * Warn on ECC error that has been fixed
- Link active Linux, SMART, ZFS, and ECC templates to `private-cloud-zabbix`, the Zabbix host name from the service catalog
- Maintain the Dataset capacity dashboard from the enabled dataset catalog
- Alert on stale collectors, old snapshots, overdue scrubs, and unavailable ECC telemetry
- Email Warning, Average, High, and Disaster problems through the configured relay when notifications are enabled
- Use native stdout/stderr for Zabbix containers
- Send Zabbix problem, recovery, and hourly reminder emails to the local Stalwart mailbox
- Retry Zabbix email delivery up to ten times at one-minute intervals
- Pause Zabbix notifications for suppressed problems during maintenance

### Alloy log collection

- Emit a host logging heartbeat to detect missing collection during quiet periods
- Deploy digest-pinned Grafana Alloy as one node collector in observability
- Create tank/secure/no-backup/k0s/services/alloy with a configurable 5G initial quota and dedicated 10Ti PV/PVC
- Collect workload containers, init containers, sidecars, host journal entries, and Kubernetes events
    * Retain journal records for the kernel, k0s, ZFS, SSH, Zabbix Agent, systemd units, and logging heartbeat
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

### OpenObserve

- Use local username/password login over HTTPS for diagnostic access without Keycloak OIDC or Dex
- Evaluate log alert rules and send their notifications in OpenObserve

#### Storage and queries

- Deploy one digest-pinned OpenObserve 0.90.3 node in observability
- Create tank/secure/no-backup/k0s/services/openobserve with a configurable 50G initial quota and dedicated 10Ti PV/PVC
- Use OpenObserve local mode with disk object storage and SQLite metadata
- Retain logs for a configurable 14 days by default through OpenObserve compaction
- Return 1,000 query rows by default and activate the memory circuit breaker at 90%
- Use native stdout/stderr logging for collection by Alloy

#### Log alert rules and delivery

- Evaluate four rules in the logs stream every minute over the preceding five minutes
    * Warning: trigger on at least one entry with normalized warn severity
    * Error: trigger on at least one entry with normalized error severity
    * Critical: trigger on at least one entry with normalized critical severity
    * Missing heartbeat: trigger when no host logging heartbeat appears in the window
- Include Kubernetes Warning events and classify Traefik HTTP 5xx responses as errors
- Suppress repeated notifications from each rule for five minutes
- Keep OpenObserve internal logs searchable while excluding them from severity alerts to prevent notification feedback loops
