# Application validation

Each application role runs its service validator after setup, and installer `validate` reruns the same files independently. Every check targets the installed production services and the configured public providers; the repository contains no mocks, test CAs, or endpoint overrides.

Validators trust only the distribution's Mozilla root store in `/usr/share/ca-certificates/mozilla`, so a locally installed CA cannot satisfy a TLS check. Externally configured prerequisites that remain manual are listed in [SETUP.md](SETUP.md#not-checked-automatically).

## PostgreSQL

- The validator runs a TCP `SELECT 1`, verifies pgvector and VectorChord versions, checks the configured PostgreSQL settings, and confirms the ZFS tuning and capacity.

## Meilisearch

- The validator authenticates with the configured master key and lists indexes through the Meilisearch API.

## Apache Tika

- The validator submits a text sample to `/tika` and requires the extracted text in the response.

## Bleve

- The validator confirms the dedicated Bleve PV and PVC bind to the configured dataset before OpenCloud mounts the index.
- Search indexing through OpenCloud remains an operator acceptance check.

## OnlyOffice

- The validator confirms a distinct [Kubernetes user namespace](https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/) and WOPI discovery.
- The global network check verifies the configured HTTPS hostname and public certificate.
- Opening and saving a document through OpenCloud remains an operator acceptance check.

## OpenCloud

- The validator checks issuer discovery and authenticated WebDAV upload, readback, and deletion.
- The global identity check verifies every enabled client callback.
- Browser and mobile sign-in remain operator acceptance checks.

## Grist

- The validator checks the pinned `/status` health route.
- The global network and identity checks cover the configured route and ForwardAuth client.
- Creating a document with forwarded-header identity remains an operator acceptance check.

## Manticore Search

- The validator runs `SELECT 1` through Manticore's raw HTTP SQL endpoint ([official HTTP API](https://manual.manticoresearch.com/Connecting_to_the_server/HTTP)).

## Redis for AFFiNE

- The validator writes, reads, and removes a short-lived cache value.

## AFFiNE

- The validator requests `/info` and checks pgvector in its database.
- OpenCloud sign-in and workspace creation remain operator acceptance checks.

## Immich

- The validator checks the server ping, machine-learning ping and inference, Valkey round trip, and PostgreSQL extensions.
- OpenCloud sign-in and media upload remain operator acceptance checks.

## Logging and Zabbix

- The logging validator checks both Deployments, ready endpoints, OpenObserve `/healthz`, and Alloy health, readiness, and metrics routes.
- It verifies the OpenObserve hostname, internal SMTP endpoint, disabled SMTP authentication and TLS, recipient, and managed alert rules.
- It waits for the host heartbeat and delivers a temporary alert to the configured Stalwart mailbox when notifications are enabled.
- The Zabbix server validator checks API access, the monitored host, templates, the storage dashboard, and notification settings.
- The Zabbix Agent validator checks the service, listener, item keys, collectors, SMART wrapper, Alloy endpoint, and certificates.
- Global validation checks internal SMTP relay rejection and delivers a test message plus Zabbix problem and recovery notifications.

## Storage and cluster

- ZFS validation checks the online pool, unlocked encryption root, dataset properties, native mount units, and boot ordering.
- k0s validation checks the controller, ready node, storage paths, bound volumes, and forwarding sysctl allowlist.
- The integrity check rejects local trust anchors, `/etc/hosts` overrides, CoreDNS host overrides, and injected Traefik certificates.
- It rejects workload `hostAliases`, CA environment overrides, trust-store mounts, TLS Secrets, and NetworkPolicies absent from the repository templates.

## Networking and media

- Networking validation checks Traefik, AmneziaWG, the VPN interface, firewall rules, and routes.
- It requires the production Let's Encrypt and Cloudflare endpoints in Traefik and DDNS.
- The edge check requires host split DNS to resolve each hostname to the Traefik address.
- It requires publicly trusted HTTPS and SMTP certificates with more than 14 days remaining.
- The public DNS check queries `1.1.1.1` and `8.8.8.8` for managed A records, mail MX, SPF, DMARC, and PTR.
- The media validator checks workloads, ARR APIs, download-client configuration, qBittorrent tunnel binding, and VPN health.
- It requires guarded media traffic to exit through the VPN with an address different from the home WAN address.
- Jellyfin validation checks its public information API and runs a short CPU transcoding probe.
- Intel GPU validation requires a real render device.

## Mail

- Stalwart validation waits for a server endpoint and authenticates the configured mailbox through JMAP.
- It accepts the forwarding recipient and rejects anonymous external relaying on TCP 25.
- Global validation checks public SMTP STARTTLS and delivers internal alert messages to that mailbox.
