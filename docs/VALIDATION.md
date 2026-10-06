# Application validation

Each application role runs its service validator after setup, and installer `validate` reruns the same files independently. The global network checks use configured hostnames for trusted HTTPS routes, while the identity checks verify configured OpenCloud clients and redirects.

## PostgreSQL

- The validator runs a TCP `SELECT 1`, verifies pgvector and VectorChord versions, checks the configured PostgreSQL settings, and confirms the ZFS tuning and capacity.
- The constrained VM trial uses 1GiB RAM with shared buffers at one quarter of the limit and a suggested 3–5GiB dataset quota.

## Meilisearch

- The validator authenticates with the configured master key and lists indexes through the Meilisearch API.
- The constrained VM trial uses 256MiB RAM and suggests a 1GiB dataset quota.

## Apache Tika

- The validator submits a text sample to `/tika` and requires the extracted text in the response.
- The constrained VM trial uses 512MiB RAM and suggests a 512MiB dataset quota.

## Bleve

- The validator confirms the dedicated Bleve PV and PVC bind to the configured dataset before OpenCloud mounts the index.
- Bleve is embedded in OpenCloud and has no separate pod or memory limit; the constrained VM trial suggests a 512MiB dataset quota.
- Search indexing requires an authenticated file upload and query through OpenCloud, which remains an operator acceptance check.

## OnlyOffice

- The validator confirms the pod uses a distinct [Kubernetes user namespace](https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/) and responds to WOPI discovery, and the global network check verifies the configured HTTPS hostname and certificate.
- The constrained VM trial tries 2GiB RAM and suggests a 4GiB dataset quota, below the [upstream Linux Docker guidance](https://helpcenter.onlyoffice.com/docs/installation/docs-community-install-docker.aspx) of 4GB RAM and 40GB free disk.
- Opening and saving a document through OpenCloud remains an operator acceptance check.

## OpenCloud

- The manifest sets `OC_URL` and `OC_OIDC_ISSUER` from the configured hostname, and the validator checks issuer discovery endpoints ([upstream settings](https://docs.opencloud.eu/docs/dev/server/configuration/global-environment-variables/)); the global identity check verifies client callback registration.
- The constrained VM trial uses 1GiB RAM and suggests a 2GiB dataset quota, plus Bleve's separate 512MiB dataset.
- Completing browser and mobile sign-in remains an operator acceptance check.

## Grist

- The validator checks the pinned `/status` health route, and the global network and identity checks cover the configured route and ForwardAuth client.
- The constrained VM trial uses 512MiB RAM and suggests a 1GiB dataset quota.
- Creating a document with forwarded-header identity remains an operator acceptance check.

## Manticore Search

- The validator runs `SELECT 1` through Manticore's raw HTTP SQL endpoint ([official HTTP API](https://manual.manticoresearch.com/Connecting_to_the_server/HTTP)).
- The constrained VM trial uses 256MiB RAM and suggests a 512MiB dataset quota.

## Redis for AFFiNE

- The validator writes, reads, and removes a short-lived cache value through Redis.
- The constrained VM trial uses 128MiB RAM and no dataset.

## AFFiNE

- The validator requests AFFiNE's upstream health endpoint `/info` and checks pgvector in its database.
- The constrained VM trial uses 1GiB RAM and suggests a 1GiB dataset quota; the [upstream self-host deployment](https://github.com/toeverything/AFFiNE/blob/canary/.docker/selfhost/compose.yml) specifies dependencies but no memory minimum.
- Completing OpenCloud sign-in and creating a workspace remain operator acceptance checks.

## Immich

- The validator checks the server ping, machine-learning ping, Valkey round trip, and required PostgreSQL extensions.
- The constrained VM trial uses 1GiB each for the server and CPU machine-learning service and suggests a 2GiB dataset quota.
- Upstream recommends 6GB minimum RAM and 8GB for smoother use; its 4GB guidance disables machine learning, so this VM trial proves startup only and does not exercise model inference ([requirements](https://docs.immich.app/install/requirements/)).
- Completing OpenCloud sign-in, model inference, and a media upload remain operator acceptance checks.

The 10Ti PV and PVC capacities remain fixed by repository policy; the dataset quota controls actual pool use. These low quotas and memory limits are boot-test values, not service growth targets.

## Logging and Zabbix

- The logging validator checks both Deployments, ready endpoints, OpenObserve `/healthz`, and Alloy health, readiness, and metrics routes.
- It verifies the configured OpenObserve hostname, SMTP relay, recipient, and managed alert rules.
- It waits for the host heartbeat in OpenObserve and delivers a temporary alert to the configured Stalwart mailbox when notifications are enabled.
- The Zabbix server validator checks API access, the configured monitored host, required templates, the storage dashboard, and notification settings.
- The Zabbix Agent validator checks the service, localhost listener, item keys, ZFS and ECC collectors, SMART wrapper, Alloy endpoint, and configured certificates.
- Global validation also confirms direct SMTP relay delivery and sends a temporary Zabbix problem and recovery through the configured mailbox.
- The constrained VM trial is configured for 1GiB OpenObserve, 256MiB Alloy, 1GiB Zabbix Server, and 512MiB Zabbix web limits.
- Zabbix init containers use 512MiB limits and run before their application containers.
- These configured caps are trial values and do not establish lower successful memory minimums.
- Current test dataset quotas are 2GiB for OpenObserve, 512MiB for Alloy, and 1GiB for Zabbix; they remain separate from fixed 10Ti PV capacities.
- The test does not prove external DNS, public mail routing, Cloudflare certificate renewal, or physical SMART and ECC telemetry.

## Storage and cluster

- ZFS validation checks the online pool, unlocked encryption root, dataset properties, native mount units, and boot ordering.
- The VM trial uses two 40GiB disks, a 1GiB ARC cap, and service quotas sized for startup.
- k0s validation checks the controller, ready node, configured storage paths, bound volumes, and active forwarding sysctl allowlist.
- The VM reserves 2GiB for the host before checking enabled service memory limits.

## Networking and media

- Networking validation checks Traefik, AmneziaWG, the VPN interface, firewall rules, and configured routes.
- The local HTTPS Cloudflare mock runs the real DDNS job against configured record names.
- The media validator checks each workload, ARR APIs, download-client configuration, qBittorrent tunnel binding, and VPN health.
- Jellyfin validation checks its public information API and runs a short CPU transcoding probe.
- The VM trial uses 384MiB each for Sonarr and Radarr, 256MiB for Prowlarr, 192MiB for qBittorrent, and 512MiB for Jellyfin.
- The OpenVPN gateway uses 128MiB with a 64MiB route helper and separate 64MiB DNS and log sidecars.
- Each media dataset uses a 3GiB quota to satisfy Jellyfin's startup free-space requirement.
- Intel GPU validation requires a real render device and remains a hardware acceptance step in this VM.

## Mail

- Stalwart validation waits for a server endpoint and authenticates the configured mailbox through JMAP discovery.
- Global validation checks SMTP STARTTLS and delivers relay messages to that mailbox.
- The VM trial uses a 512MiB memory cap and a 1GiB dataset quota.
- The local ACME server registers accounts and signs configured-hostname certificate requests with the test CA.
- Domain ownership challenges and JWS verification are mocked in the local ACME fixture.
- The real ACME provider rejected the reserved `.test` contact address during this run.
