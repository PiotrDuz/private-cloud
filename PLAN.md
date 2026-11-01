# Whole-system target specification

This file is the source of truth for the desired system state and its major decisions.

## Table of contents

- [System configuration](#system-configuration)
    * [TPM unattended unlock](#tpm-unattended-unlock)
- [ZFS storage](#zfs-storage)
- [k0s cluster](#k0s-cluster)
- [PostgreSQL](#postgresql)
- [Shared identity](#shared-identity)
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
    * [AirVPN WireGuard gateway](#airvpn-wireguard-gateway)
- [Jellyfin](#jellyfin)
- [Security](#security)
- [Networking](#networking)
    * [Public entry and DNS](#public-entry-and-dns)
    * [LAN DNS](#lan-dns)
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

## System configuration

- Encrypt the root disk with LUKS2 and keep a recovery passphrase
- Keep the tank/secure key file on the encrypted root
- Disable all swap, including disk-backed swap and zram
- Install kernel, firmware, and boot-chain updates only by hand
- Block DMA with strict IOMMU and kernel memory reads with lockdown
- Disable magic SysRq

### TPM unattended unlock

- Unlock the root disk at boot through the TPM without operator input
- Boot only an owner-signed UKI under Secure Boot, without shim or GRUB
- Keep Secure Boot signing keys off the host
- Hold the unattended root key in TPM NV memory, readable once per boot
- Bind the key to PCRs 0, 2, 4, 7, 11, and a salted PCR 15 inventory of hardware and the gateway
- Wipe the key on a failed check, a gateway change, or a USB attach
- Wipe the key and power off when the gateway stays silent for 2 minutes at boot
- Power off after a runtime wipe and never reboot from a check
- Disable initrd shells
- Disable console login and external USB devices while armed
- Authorize only the storage interface of a USB system disk and the hubs on its path
- Run no checks in the wiped state and allow console login with the administrator password
- Re-enroll the key by hand after each boot-chain update

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
- Limit each pod to 4096 processes and threads
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

## Shared identity

- Use Stalwart's [OpenID Connect provider](https://stalw.art/docs/auth/oauth/openid-connect) and internal directory for shared login
- Manage accounts, passwords, and suspension in Stalwart
- Use the Stalwart HTTPS URL as the shared issuer through the LAN DNS service
- Register OAuth clients in Stalwart for OpenCloud, Immich, AFFiNE, and Grist's authentication helper
    * Pin ES256 ID token signatures for verification through the published JWKS
    * Add CORS on the Stalwart OAuth endpoints for OpenCloud Web
- Store confidential-client secrets in role-owned Kubernetes Secrets and keep public clients secret-free
- Allow every Stalwart account to sign into connected applications without separate login allowlists
- Make the managed Stalwart mailbox account the administrator of OpenCloud, Grist, AFFiNE, and Immich
- Keep permissions and administrator grants within each application
- Delete accounts manually in Stalwart and each downstream application
- Remove user-owned data and revoke credentials during each application's account deletion
- Preserve data when disabling accounts and preserve resources owned by other users during deletion
- Keep Stalwart, Jellyfin, the ARR stack, Zabbix, OpenObserve, and the AmneziaWG UI on native passwords
- Keep AmneziaWG peers on keys generated in its UI
- Keep backend APIs, database connections, mail transport, and log ingestion on service credentials
- Keep internal services without interactive logins private

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
- Use Stalwart's internal directory with native mailbox and administrator passwords
- Manage mailboxes, aliases, quotas, and permissions in Stalwart
- Publish JMAP, web access, and management through Traefik HTTPS TCP 443
- Follow the external INBOX read-only over IMAP IDLE from a sidecar in the Stalwart pod
- Start after the newest provider message and never flag, move, or delete provider mail
- Deliver new mail to the mailbox over loopback SMTP with Proxy Protocol v2 naming the original client
- Take the original client from the provider's own top Received headers so SPF and iprev see the real sender
- Publish no inbound SMTP port
- Use Let's Encrypt DNS-01 and a dedicated Cloudflare token for the Stalwart certificate
- Keep IMAPS 993 and submission ports 465 and 587 unexposed
- Configure the inbox.eu SMTP relay
    * Deliver local-domain mail locally and route other outbound mail through inbox.eu
    * Use the configured relay hostname, port, username, and implicit TLS or STARTTLS mode
    * Reject invalid relay certificates
    * Supply the relay password through the Stalwart runtime Secret
    * Use the configured notification sender address for alert emails
    * Address alerts to `<stalwart.mailbox_username>@<domain>`
    * Send OpenObserve and Zabbix alerts directly to Stalwart's internal SMTP listener on TCP 2525
    * Use plain SMTP without authentication for internal alerts
    * Restrict internal alert SMTP ingress and egress to OpenObserve, Zabbix, and Stalwart pods
    * Reject anonymous external relaying on the internal SMTP listener
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
- Authenticate document users through the OpenCloud session and its WOPI access tokens
- Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
- Use OnlyOffice 9.4.0.1's native entrypoint to forward /var/log/onlyoffice to container output without a logging sidecar
- Persist source logs on the OnlyOffice dataset
- Check source rotation every 15 minutes with a 10MiB limit and seven-day retention
- Run container root inside a Kubernetes user namespace

## OpenCloud

- Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
- Authenticate OpenCloud web, desktop, and mobile clients through Stalwart OIDC
- Create built-in directory users on first sign-in and match them by email
- Bind the built-in administrator to the managed Stalwart mailbox account
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
- Use [Grist forwarded-header authentication](https://support.getgrist.com/install/forwarded-headers/) through Traefik and a Stalwart OIDC ForwardAuth helper
    * Set `GRIST_FORWARD_AUTH_HEADER=X-Forwarded-User` to receive the authenticated user's email
    * Authenticate every Grist request through the helper and route its sign-in, callback, and logout endpoints on the Grist hostname
- Use Stalwart account addresses for Grist accounts and keep document permissions in Grist
- Use a single Grist team site for the supported forwarded-header login flow
- Limit Grist access to authenticated browser sessions without API-key access
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
- Configure [AFFiNE OIDC sign-in](https://affine.pro/enterprise) with Stalwart through its server configuration file
    * Keep the self-hosted OIDC sign-in licence-free within ten seats
- Configure its confidential client, issuer, email claims, and HTTPS `/oauth/callback` redirect
- Permit AFFiNE's OIDC client to reach only the trusted Stalwart issuer when it resolves to a private address
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
- Enable [Immich native OIDC](https://docs.immich.app/administration/oauth/) with Stalwart for web and mobile clients
- Register a confidential client with HTTPS `/auth/login`, `/user-settings`, and `/api/oauth/mobile-redirect` redirects
- Use the Immich mobile redirect override so mobile sign-in returns through an HTTPS redirect
- Automatically register Stalwart users in Immich and manage administrator grants explicitly
- Use supported provider logout and manage account permissions within Immich
- Use native stdout/stderr logging for collection by Alloy
- Run container root inside a Kubernetes user namespace

## ARR stack

- Keep Sonarr, Radarr, Prowlarr, qBittorrent, and VPN gateway templates under k0s-services/arr
- Deploy the ARR stack in the media namespace through the media installer stage
- Give Sonarr, Radarr, Prowlarr, and qBittorrent a dataset under tank/secure/no-backup/k0s/services/<service> with a quota and a dedicated 10Ti PV
- Keep the VPN gateway stateless without a dataset
- Create the shared media-library dataset under tank/secure/no-backup/k0s/services/media-library with a quota and a dedicated 10Ti PV
- Keep dashboards, peer ports, and discovery protocols unpublished, except the LAN-only Radarr, Prowlarr, and Bazarr UIs
- Connect Prowlarr, Sonarr, Radarr, and qBittorrent automatically with native API keys and a Vault-managed qBittorrent password
- Run a stateless FlareSolverr behind the media VPN as Prowlarr's Cloudflare challenge proxy
- Run Bazarr behind the media VPN, connected to Sonarr and Radarr, with a no-backup dataset
- Keep Sonarr, Radarr, Prowlarr, the VPN gateway, and network helpers on native console output
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

### AirVPN WireGuard gateway

- Route guarded media external traffic and DNS through an AirVPN WireGuard tunnel, with qBittorrent in the gateway pod on a forwarded port and per-pod tun2socks helpers for the other applications
- Block direct Internet fallback when the VPN fails
- Select AirVPN servers by configured country from gluetun's built-in server list without DNS outside the tunnel
- Let gluetun's firewall pin traffic outside the tunnel to the selected server's WireGuard UDP port
- Cap the gateway NetworkPolicy at the AirVPN WireGuard UDP port on public addresses
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
- Use native Jellyfin username/password login and manage library permissions in Jellyfin
- Keep native [Quick Connect](https://jellyfin.org/docs/general/server/quick-connect/) available for supported clients
- Apply library settings before Jellyfin starts
- Keep online metadata and image download enabled while disabling subtitle, unrelated plugin, and remote-media integrations
- Use native console logging without a logging sidecar
- Keep separate FFmpeg diagnostic logs on the Jellyfin dataset
- Let Jellyfin's Clean Log Directory task delete FFmpeg diagnostics after three days

## Security

- Run ordinary application containers with fixed non-root UIDs and disabled privilege escalation
- Claim Immich, AFFiNE, and Jellyfin administrators through the installer before publishing their routes
    * Run AFFiNE, Immich server, and OnlyOffice container root inside Kubernetes user namespaces
    * Run Jellyfin and the ARR applications as a dedicated media UID that no host account uses
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
- Use Stalwart as the shared identity source for OIDC-enabled applications while retaining application-specific authorization
- Keep host and Kubernetes administration on their own credentials and workload identities
- Keep ingestion credentials separate from OpenObserve administrator credentials
- Keep media VPN isolation independent of log collection

## Networking

### Public entry and DNS

- Maintain configured public A records with a dedicated Cloudflare DDNS token
- Derive every service hostname from one base domain
- Keep the primary domain's mail with the external inbox provider
- Serve a homepage at `www.<domain>` with a named icon tile for each enabled application UI, split into apps and administration
- Use `mx-inbound.<domain>` as the Stalwart hostname

### LAN DNS

- Run a CoreDNS LAN resolver in dns-system on host TCP and UDP 53 for local networks
- Answer every service hostname and the AmneziaWG UI hostname with the host LAN address
- Answer cluster DNS with the Traefik Service address so pods skip the router and the host port
- Point the kubelet upstream resolver at the LAN DNS Service so k0s CoreDNS stays unmodified
- Forward other queries to public resolvers over DNS-over-TLS
- Answer Firefox, Apple Private Relay, and DDR encrypted DNS canaries with NXDOMAIN
- Give AmneziaWG peers the host LAN address as their DNS server
- Keep the LAN resolver stateless without a dataset

### Traefik

- Deploy Traefik with host TCP 443 for HTTPS
- Publish application services as ClusterIP endpoints behind exact Traefik host rules
- Configure Traefik routes through the file provider without Kubernetes API access
- Obtain Traefik HTTPS certificates with Cloudflare DNS-01
- Give Traefik a quota-controlled backup dataset and a dedicated 10Ti PV/PVC
- Enable structured Traefik service and access logs on stdout
- Disable the Traefik dashboard and leave unknown HTTPS hosts without a route
- Run a stateless nginx homepage in edge from a generated ConfigMap
- Run a stateless [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) helper in edge for Grist's Stalwart OIDC login
- Keep the helper's OIDC client secret and cookie-signing secret in Kubernetes Secrets
- Configure ForwardAuth to pass the authenticated email to Grist through `X-Forwarded-User`
- Strip incoming identity headers before authentication and forward only the helper's verified identity
- Give the helper a dedicated confidential OpenCloud client without separate email or domain allowlists
- Handle Grist login, OIDC callbacks, and logout without an authentication redirect loop
- Preserve native application authentication for OIDC APIs, mail protocols, and WOPI callbacks

### Host access and service isolation

- Restrict SSH, the Kubernetes API, Zabbix TCP 31051, and DNS 53 to local networks
- Permit only TCP 443, the AmneziaWG UDP port, ICMP, and DHCP from untrusted networks
- Drop traffic from interfaces other than loopback, the default interface, and pod networking
- Block obsolete application NodePorts and undeclared host ports
- Label managed namespaces and enforce default-deny ingress and egress with explicit exceptions
- Permit application dependencies only through declared service ports and namespace selectors
- Permit OIDC-enabled services and the edge ForwardAuth helper to reach Stalwart for discovery, token exchange, user information, and signing keys
- Permit provider logout callbacks only for supported and configured flows

### Namespace and host placement

- Place application services, their databases, search dependencies, and Zabbix in private-cloud
- Place Sonarr, Radarr, Prowlarr, qBittorrent, the VPN gateway, and Jellyfin in media
- Place Traefik in edge, AmneziaWG in network-access, and Cloudflare DDNS and LAN DNS in dns-system
- Place Alloy and OpenObserve in observability
- Keep CNI, cluster DNS, and the GPU device plugin in kube-system
- Keep ZFS, the host firewall, Zabbix Agent, and journal collection support on the host

### VPN and media routing

- Run AmneziaWG with the userspace amneziawg-go implementation so no host kernel module is needed
- Keep AmneziaWG routing, NAT, and peer firewall rules inside its pod network namespace
- Route guarded media application egress through the AirVPN WireGuard gateway with fail-closed policies
- Keep Jellyfin ingress behind Traefik and allow direct Internet metadata egress
- Cap AmneziaWG peers at configured LAN destinations, peer DNS, Traefik, and public Internet through its NetworkPolicy
- Deny AmneziaWG peer access to other peers, pod CIDRs, service CIDRs, and media APIs

### AmneziaWG

- Deploy AmneziaWG through wg-easy in the network-access namespace with a configured UDP hostPort
- Force wg-easy's AmneziaWG mode onto the bundled userspace amneziawg-go
- Generate the server key and obfuscation values on first start
- Create the UI administrator from Vault on first start
- Manage peers, client keys, QR codes, and per-peer firewall entries in the UI
- Publish the UI through Traefik only to local networks and VPN peers
- Keep the UI database on its own dataset, quota, and 10Ti PV
- Block peer-to-peer forwarding in the mangle table so UI edits cannot reopen it
- Use native stdout/stderr logging for collection by Alloy

## Observability

### System-wide requirements

- Probe every workload container for readiness and liveness so unhealthy containers restart or leave service
    * Exempt init containers, Jobs, CronJobs, and host device plugins
- Preserve unclassified messages as investigation evidence without assigning an alert level
- Track metric alerts as Zabbix problems with deduplication, recovery, and recurring reminders
- Send log alerts as throttled event notifications without recovery or reminder emails
- Email every Warning-or-higher alert through the mail service
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
    * CPU, memory, and container restarts per Kubernetes workload every minute
- Route Zabbix Agent and host collector diagnostics through system logging, the journal, and Alloy into OpenObserve

#### Zabbix k0s service

- Deploy Zabbix server with its own dataset, quota, and 10Ti PV in the cluster
- Zabbix service creates its database, login role, and credentials Secret
- Connect Zabbix to its database
- Use local username/password login over HTTPS for the Zabbix web interface
- Expose the Zabbix server port to the host metrics gatherer
- Alert thresholds
    * Warn when tank usage exceeds 80% and raise a high alert above 90%
    * Warn on service dataset quota utilization at 80% and raise high alerts for fixed leaf datasets at 90%
    * Alert on SMART disk low health through the linked stock SMART template
    * Alert on unfixed ZFS error
    * Warn on ZFS error that has been fixed (scrub or normal operation)
    * Alert on unfixed ECC error
    * Warn on ECC error that has been fixed
- Link active Linux, SMART, ZFS, ECC, and Kubernetes workload templates to `private-cloud-zabbix`, the Zabbix host name from the service catalog
- Maintain the Private cloud dashboard with Overview, Storage, Dataset capacity, Disks, Workloads, and Services pages
    * Build the Dataset capacity page from the enabled dataset catalog
- Alert on stale collectors, old snapshots, overdue scrubs, and unavailable ECC telemetry
- Email Warning, Average, High, and Disaster problems directly to Stalwart when notifications are enabled
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

- Use local username/password login over HTTPS for diagnostic access without an SSO helper
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

- Suppress repeated notifications from each rule for sixty minutes
- Keep OpenObserve internal logs searchable while excluding them from severity alerts to prevent notification feedback loops
