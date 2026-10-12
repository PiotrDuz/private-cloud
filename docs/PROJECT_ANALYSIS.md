# Private cloud project analysis

Last updated: 11 October 2026.

Source baseline: `a4e6b58` (`Fixes and rearrangement`). No implementation has changed since the first version of this report, so every earlier finding still applies.

This revision adds a service-by-service review of every template in `k0s-services/` against [PLAN.md](../PLAN.md). It also simplifies the report: each issue is described in general terms, with the affected files named so it can be traced.

## Summary

The architecture is coherent and largely follows PLAN.md. Good foundations are already in place:

- Encrypted ZFS storage with per-service datasets, quotas, and fixed local volumes.
- Public configuration kept separate from Vault-encrypted secrets.
- Default-deny network policies with explicit per-service exceptions.
- Restrictive pod security settings for most workloads.
- Verified identity headers for Grist.
- An internal alert SMTP path that confirms delivery by reading the destination mailbox.
- Functional service validators.

The project is **not yet ready for Internet exposure or important data**. The main reasons are:

1. **Installation and recovery blockers.** ZFS monitoring rejects its own inventory, pool validation fails on normal pools, and a failed first install cannot be resumed.
2. **Certificates may never be issued.** Traefik's network policy blocks the DNS queries that the ACME DNS-01 check needs (new finding).
3. **Admin takeover window.** Immich, AFFiNE, Jellyfin, and Zabbix are published before their first administrator is claimed.
4. **Over-trusted components.** OnlyOffice holds OpenCloud's WOPI signing secret, accepts any WOPI host, and Traefik can read every Secret in the cluster.
5. **Monitoring gaps.** The missing-heartbeat alert can never send, and log alerts have no recovery or reminder handling.
6. **No backups.** RAIDZ1 is not a backup, and backup automation is deferred.

## How to read this report

| Severity | Meaning |
| --- | --- |
| High | Blocks installation or recovery, exposes administration or credentials, or hides a monitoring failure. |
| Medium | Breaks a supported feature, weakens a security boundary, or contradicts PLAN.md under realistic conditions. |
| Low | Hygiene, hardening, or consistency issue with limited direct impact. |

Status labels:

- **Confirmed**: the source contains the problem.
- **Likely**: the source strongly suggests failure, but the result depends on runtime behavior that a live test should confirm.
- **Conditional**: the problem appears only with a specific configuration or lifecycle action.

Finding IDs F01–F27 come from the first version of this report and keep their numbers. F28–F36 are new.

## Issues at a glance

| ID | Sev. | Area | Issue |
| --- | --- | --- | --- |
| F01 | High | Install | ZFS collector rejects the installer configuration dataset. |
| F02 | High | Install | Pool validation compares ZFS partitions with whole disks. |
| F08 | High | Install | A failed early `create` cannot be resumed. |
| F07 | High | Install | Custom pod, service, and DNS network values are never applied to k0s. |
| F28 | High | Networking | ACME DNS-01 propagation checks are blocked by egress policy. **New** |
| F18 | High | Networking | Pods cannot reach Traefik through the host port the policies allow. |
| F04 | High | Security | Public routes expose first-administrator setup. |
| F05 | High | Security | Public OnlyOffice accepts any WOPI host. |
| F29 | High | Security | OnlyOffice holds OpenCloud's WOPI token-signing secret. **New** |
| F13 | High | Security | Traefik can read Secrets in every namespace. |
| F03 | High | Lifecycle | Three advertised secret rotations are incomplete. |
| F19 | High | Identity | AFFiNE has no public URL configured. |
| F06 | High | Alerts | Missing-heartbeat alert can never send. |
| F09 | Medium | Lifecycle | Disabling a stage leaves its service running and public. |
| F10 | Medium | Lifecycle | Disabling networking breaks validation and removes default-deny. |
| F12 | Medium | Lifecycle | Sonarr, Radarr, and Prowlarr can run two writers during updates. |
| F11 | Medium | Identity | Grist logout lands on a protected page and logs back in. |
| F20 | Medium | Identity | Grist session identity and proxy identity can disagree. |
| F21 | Medium | Identity | Grist API keys cannot work through ForwardAuth. |
| F30 | Medium | Identity | The Grist login helper is unmaintained. **New** |
| F27 | Medium | Identity | Identity validation treats any HTTP success as a working callback. |
| F22 | Medium | Security | Zabbix accepts unauthenticated agent data from the LAN. |
| F23 | Medium | Security | Admin passwords have no strength floor or default rejection. |
| F25 | Medium | Security | Jellyfin and Stalwart see Traefik's address instead of the client's. |
| F31 | Medium | Security | Stalwart uses the Meilisearch master key. **New** |
| F14 | Medium | Mail | Pinned Stalwart release has an unenforced queue-quota bug. |
| F17 | Medium | DNS | DDNS does not fix wrong proxy or TTL settings. |
| F15 | Medium | Alerts | Log alerts have no incident, recovery, or reminder handling. |
| F16 | Medium | Validation | Policy validation checks names, not contents. |
| F24 | Medium | Logging | Journal filter drops sudo, login, and firewall events. |
| F32 | Medium | Storage | Jellyfin re-owns the whole media library on every start. **New** |
| F26 | Low | Security | Pod annotations contain raw secret hashes. |
| F33 | Low | Supply chain | Many images are not digest-pinned; OpenCloud uses the rolling channel. **New** |
| F34 | Low | Config | Service-link variables collide with Stalwart and Grist environment prefixes. **New** |
| F35 | Low | Security | OpenObserve admin and ingestion credentials share one Secret. **New** |
| F36 | Low | Security | AFFiNE and OnlyOffice keep the full default capability set. **New** |

## Issues by area

### Installation and recovery

**F01 — ZFS monitoring rejects its own inventory (High, confirmed).**
The service catalog includes the installer configuration dataset `tank/secure/backup/private-cloud-config`. The ZFS collector only accepts datasets under `.../k0s/...`, so it fails before collecting anything. Zabbix Agent validation then fails on every normal installation.
*Fix:* let the collector accept the exact configuration dataset, and share one allowed-path definition between the catalog and the collector.
Files: `ansible/service_catalog.yml`, `zabbix/zabbix-zfs-collector.py`.

**F02 — Pool validation confuses disks and partitions (High, confirmed).**
ZFS reports whole-disk pools by their partitions (for example `/dev/sdb1`), but the check compares those paths with the selected whole disks (`/dev/sdb`). A correct pool can therefore fail preflight, which blocks reapply, update, and rotate.
*Fix:* map each partition to its parent disk before comparing. Keep the check, because it guards destructive operations.
File: `ansible/storage_checks.py`.

**F08 — A failed first install cannot be resumed (High, conditional).**
`create` refuses an existing pool, and the other modes require the stored configuration. A failure after the pool is created but before the configuration is saved leaves a state the installer rejects.
*Fix:* record the create intent before destructive work, and allow a narrow resume when the existing pool matches it.
File: `ansible/install.py`.

**F07 — Custom network ranges are accepted but never applied (High, conditional).**
The installer validates custom pod CIDR, service CIDR, and cluster DNS values. The firewall, VPN, and DNS configuration use them, but the k0s configuration keeps its defaults. Any non-default value breaks routing and isolation.
*Fix:* write the values into the k0s config before first start, and reject later changes.
File: `ansible/roles/k0s/tasks/main.yml`.

### Networking

**F28 — Certificate issuance is likely blocked by egress policy (High, likely). New.**
Traefik's egress policy allows only TCP 443 to the Internet. During DNS-01, Traefik's ACME library (lego) checks propagation by querying the zone's authoritative nameservers directly on port 53. Those queries are dropped, so the challenge can time out and no certificate is issued. The live trial used a mock ACME server, so this path was never exercised. Stalwart's own DNS-01 issuance should be checked for the same dependency, because its policy also allows only the relay port and 443.
*Fix:* choose one of these:
- Allow UDP and TCP 53 to public addresses for Traefik, and for Stalwart if needed.
- Configure Traefik's DNS challenge to skip authoritative-nameserver checks and use a propagation delay instead.

Then observe a real issuance and renewal.
Files: `k0s-services/networking/templates/traefik.yaml.j2`, `k0s-services/networking/templates/private-cloud-egress.yaml.j2`.

**F18 — Pods cannot reach Traefik through the allowed address (High, likely).**
OpenCloud, OnlyOffice, AFFiNE, Grist, Immich, and ForwardAuth reach the public hostname through the node's port 443. Policies allow only `node-IP:443`, but host-port translation rewrites the destination to the Traefik pod on 8443 before the policy is checked. OIDC discovery, token exchange, and WOPI callbacks can fail as a result. AmneziaWG's policy already contains the correct exception.
*Fix:* add egress to the Traefik pod on TCP 8443 for these clients, following the AmneziaWG pattern.
Files: `private-cloud-egress.yaml.j2`, `forward-auth.yaml.j2`.

**F17 — DDNS fixes addresses but not record settings (Medium, confirmed).**
A record is updated only when its IP differs. A record with the right IP but Cloudflare proxying turned on, which breaks SMTP, or with the wrong TTL is never corrected. Any syntactically valid IPv4 address is also published, even a private one.
*Fix:* compare content, proxy status, and TTL. Reject non-public addresses before updating.
File: `k0s-services/networking/templates/ddns-script.yaml.j2`.

**F10 — Networking is optional but required everywhere (Medium, conditional).**
The catalog allows k0s without networking. However, default-deny policies are owned by the networking stage, and global validation always reads a networking ConfigMap.
*Fix:* move baseline default-deny into the cluster stage and make edge validation conditional, or make networking mandatory.

### Security

**F04 — Administrator setup is publicly reachable (High, confirmed).**
Immich, AFFiNE, and Jellyfin are published before anyone claims their first administrator. Each lets the first visitor create the admin account. Zabbix is briefly reachable with `Admin`/`zabbix` before the installer changes the password.
*Fix:* keep these routes restricted, for example to the LAN, until administrator setup completes, then publish them.

**F05 — OnlyOffice accepts any WOPI host (High, confirmed).**
OnlyOffice is public with WOPI enabled and no trusted-host restriction. Anyone can point it at their own WOPI server and use the editor and conversion resources. OpenCloud also disables WOPI proof-key checking.
*Fix:* restrict WOPI to the OpenCloud hostname using OnlyOffice's host filtering.

**F29 — OnlyOffice holds the key that signs OpenCloud's WOPI tokens (High, confirmed). New.**
OpenCloud's `COLLABORATION_WOPI_SECRET` is read from the `onlyoffice-credentials` Secret, the same value as OnlyOffice's `JWT_SECRET`. The WOPI secret signs the access tokens that grant file access in OpenCloud. OnlyOffice is the most exposed component: it is public, processes untrusted documents, runs as root inside a user namespace, and is affected by F05. If it is compromised, an attacker can mint WOPI tokens for any file.
*Fix:* generate a separate WOPI secret that only OpenCloud receives.
Files: `k0s-services/opencloud/templates/deployment.yaml.j2`, `k0s-services/onlyoffice/templates/deployment.yaml.j2`.

**F13 — Traefik can read every Secret (High, confirmed).**
A ClusterRole grants Traefik `get`, `list`, and `watch` on Secrets cluster-wide. Compromise of the Internet-facing edge would expose every application credential.
*Fix:* use namespace-scoped Roles for the namespaces Traefik serves, and keep only cluster-scoped discovery permissions in the ClusterRole.
File: `k0s-services/networking/templates/traefik-rbac.yaml.j2`.

**F31 — Stalwart uses the Meilisearch master key (Medium, confirmed). New.**
Stalwart receives `MEILI_MASTER_KEY`, which grants full administration of Meilisearch, including key management. PLAN.md asks for service credentials for backend APIs.
*Fix:* create a scoped Meilisearch API key for Stalwart's indexes and pass only that key.
File: `k0s-services/stalwart/templates/statefulset.yaml.j2`.

**F22 — Zabbix accepts unauthenticated agent data (Medium, confirmed).**
Agent and server use unencrypted, unauthenticated transport, and the trapper NodePort 31051 is reachable from the LAN. Any LAN client could submit fake monitoring data.
*Fix:* use a PSK stored in Vault for the agent and the host object.

**F23 — Weak admin passwords are accepted (Medium, confirmed).**
OpenCloud, Stalwart, and Zabbix admin passwords have no length floor, and vendor defaults are not rejected.
*Fix:* enforce a minimum length, reject known defaults, and offer generated passwords.

**F25 — Applications see the proxy as the client (Medium, confirmed).**
Jellyfin has no known-proxy setting, and Stalwart's HTTP listener does not trust forwarded headers from Traefik. Remote and local classification, rate limits, and audit logs then see Traefik's address.
*Fix:* configure each application to trust forwarded headers only from Traefik.

**F26 — Raw secret hashes appear in pod annotations (Low, confirmed).**
The qBittorrent pod annotation is a plain SHA-256 of its password. The Immich annotation hashes the public hostname plus the OIDC client secret, which is equivalent to a plain hash of the secret. Alloy can read all pod metadata. A weak password becomes an offline guessing target.
*Fix:* use a keyed HMAC or a generated revision value instead of a direct hash.

**F35 — Admin and ingestion credentials share one Secret (Low, confirmed). New.**
The `openobserve-ingest` Secret holds both the OpenObserve root password and Alloy's ingestion passcode. Alloy mounts only its own keys, but anyone who can read that Secret gets both. PLAN.md asks for separate credentials.
*Fix:* split them into two Secrets.

**F36 — User-namespaced containers keep all default capabilities (Low, confirmed). New.**
AFFiNE and OnlyOffice neither drop capabilities nor disable privilege escalation. PLAN.md asks to drop everything except the startup capabilities they need. The user namespace limits the impact, but the contract is not met.
*Fix:* drop `ALL` and add back only what each image needs, such as `CHOWN`, `SETUID`, and `SETGID`.

### Identity and login

**F19 — AFFiNE does not know its public URL (High, confirmed).**
No external URL is configured, so AFFiNE defaults to `http://localhost:3010`. Links, OAuth redirects, and CORS origin checks can be wrong.
*Fix:* set the external URL to `https://<affine hostname>` before startup.

**F11 — Grist logout logs back in (Medium, confirmed).**
After logout, the user is redirected to `/signed-out`, which is protected by ForwardAuth. With an active OpenCloud session, the browser logs straight back in.
*Fix:* serve an unprotected signed-out route.

**F20 — Grist can keep an old user's session (Medium, confirmed).**
Grist uses session mode, while ForwardAuth authenticates every request. If the proxy identity changes, Grist can keep the previous user's session.
*Fix:* set `GRIST_IGNORE_SESSION=true` for header-per-request mode, or restrict ForwardAuth to the login paths.

**F21 — Grist API keys cannot be used (Medium, confirmed).**
All paths, including `/api/`, require a ForwardAuth browser cookie, so API clients cannot authenticate with Grist keys.
*Fix:* decide whether API access is supported. If it is, add an `/api` route that bypasses ForwardAuth but still strips identity headers.

**F30 — The Grist login helper is unmaintained (Medium, confirmed). New.**
`thomseddon/traefik-forward-auth:2.2.0` is from 2020, and the project is no longer actively maintained. It sits on the public authentication path, which makes F11 and F21 harder to fix.
*Fix:* move to a maintained OIDC proxy, such as oauth2-proxy, as part of fixing F11, F20, and F21.

**F27 — Identity checks overstate success (Medium, confirmed).**
The validator counts any 200, 302, or 303 response as an accepted client, including OAuth error pages and error redirects.
*Fix:* inspect redirect targets and error parameters, and add a negative test with a wrong callback.

### Lifecycle and configuration

**F03 — Advertised rotations are incomplete (High, confirmed).**
Three advertised rotations do not fully take effect:
- The AFFiNE database rotation never changes the PostgreSQL role password.
- The Cloudflare ACME token rotation does not restart Traefik.
- The Grist cookie-secret rotation does not restart ForwardAuth.

*Fix:* alter the role password, and add secret checksums to the Traefik and ForwardAuth pod templates.

**F09 — Disabling a stage does not stop it (Medium, confirmed).**
A disabled stage is skipped rather than removed. Its Deployments and Ingresses keep running and stay public, but drop out of validation and monitoring.
*Fix:* stop and unpublish disabled services while keeping their data, or refuse to disable an installed stage.

**F12 — ARR apps can run two writers during updates (Medium, confirmed).**
Sonarr, Radarr, and Prowlarr use the default rolling update. The old and new pods can open the same SQLite database at the same time.
*Fix:* use `strategy: Recreate` for them, as qBittorrent already does.

**F32 — Jellyfin re-owns the whole media library on every start (Medium, confirmed). New.**
The Jellyfin pod sets `fsGroup: 1000` without `fsGroupChangePolicy: OnRootMismatch`. The media library volume is read-only only at the mount, not at the PVC. On every start, kubelet therefore recursively changes group ownership and permissions across the shared library. Startup slows as the library grows, and the library Sonarr, Radarr, and qBittorrent write to keeps getting modified.
*Fix:* add `fsGroupChangePolicy: OnRootMismatch`, and mark the library PVC volume `readOnly: true` in the Jellyfin pod.
File: `k0s-services/jellyfin/templates/workloads.yaml.j2`.

**F34 — Service links collide with application variables (Low, likely). New.**
`k0s-services/AGENTS.md` asks to disable service links when a Service name collides with application environment variables. The `stalwart` and `stalwart-headless` Services inject `STALWART_*` variables into Stalwart pods, which already use the `STALWART_` prefix. The `grist` Service injects `GRIST_*` variables into Grist. Immich already disables service links.
*Fix:* set `enableServiceLinks: false` on Stalwart and Grist.

**F33 — Image pinning is inconsistent (Low, confirmed). New.**
These images use tags only: OpenCloud, OnlyOffice, Grist, Manticore, Meilisearch, Tika, Zabbix server and web, `postgres:18.4-bookworm`, and `alpine:3.22.1`. OpenCloud uses `opencloud-rolling`, the fast-moving channel, rather than the stable image.
*Fix:* pin by tag and digest everywhere, and use OpenCloud's stable image.

**F14 — Stalwart has a known queue-quota bug (Medium, upstream).**
The pinned 0.16.22 does not enforce some queue quotas. The bug is fixed in 0.16.25.
*Fix:* upgrade with a reviewed digest, then re-run mail validation.

### Observability

**F06 — Missing-heartbeat alert can never send (High, confirmed).**
The rule fires on "zero rows", but OpenObserve 0.90.3 sends notifications only when the result has rows. A silent collection outage goes unnoticed.
*Fix:* use an aggregate query that always returns a row, such as `count(*)`, and alert when the count is 0.

**F15 — Log alerts are throttled events, not incidents (Medium, confirmed).**
PLAN.md expects deduplication while a problem is open, recovery emails, and reminders. The OpenObserve rules only send one email per rule per hour, shared across all services. Certificate monitoring also depends on the logging stage being enabled.
*Fix:* either narrow PLAN.md to throttled event alerts or implement per-service incidents. Decouple certificate checks from logging.

**F24 — Host security events are not collected (Medium, confirmed).**
The Alloy journal filter drops `sudo`, `su`, `login`, and the firewall unit.
*Fix:* add those identifiers to the keep rule.

**F16 — Policy validation checks names only (Medium, confirmed).**
A deleted or weakened NetworkPolicy passes validation as long as its name is known.
*Fix:* compare rendered policy specifications, and require mandatory policies to exist.

## PLAN.md conformance by service

✅ means the service matches PLAN.md apart from the listed issues. ⚠️ means it deviates from PLAN.md.

| Service | Status | Notes |
| --- | --- | --- |
| ZFS | ⚠️ | Layout, encryption, scrub, trim, and properties match. F01, F02, and F08 block monitoring and recovery. |
| k0s | ⚠️ | Pinned version, log rotation, and quotas match. F07 leaves custom CIDRs unapplied. |
| PostgreSQL | ✅ | ZFS and PostgreSQL tuning, VectorChord image, and stderr logging match. AFFiNE role reconciliation is missing (F03). |
| OpenCloud | ⚠️ | Bleve, Tika, in-memory cache, POSIX storage, collaboration, and Draw.io match. Shares the WOPI secret with OnlyOffice (F29), uses the rolling image (F33), and pod egress may fail (F18). |
| OnlyOffice | ⚠️ | Version, user namespace, and persisted logs match. Open WOPI (F05), holds the OpenCloud secret (F29), full capability set (F36). |
| Grist | ⚠️ | PostgreSQL, Pyodide, single org, and header stripping match. Logout, session, and API issues (F11, F20, F21) and an unmaintained helper (F30). |
| AFFiNE | ⚠️ | Manticore, Redis, schema preparation, and user namespace match. No public URL (F19), open setup (F04), capabilities (F36). |
| Redis for AFFiNE | ✅ | Ephemeral, with ingress limited to AFFiNE and its preparation Job. |
| Manticore, Tika, Meilisearch | ✅ | Datasets, private ingress, and native logging match. Tags are unpinned (F33). |
| Bleve | ✅ | Dedicated PV mounted into OpenCloud. |
| Immich and Valkey | ⚠️ | VectorChord, ML with OpenVINO, OIDC, and ephemeral Valkey match. Open admin signup (F04). |
| Stalwart | ⚠️ | PostgreSQL store, Meilisearch search, SMTP proxy protocol, and internal alert listener match. Master key (F31), proxy IP (F25), version bug (F14), service links (F34), possible ACME DNS issue (F28). |
| ARR stack and OpenVPN | ⚠️ | Fail-closed VPN routing, DNS through the VPN, and qBittorrent sidecar logging match. Two writers during updates (F12), password hash annotation (F26). |
| Jellyfin | ⚠️ | Read-only library mount, GPU, Traefik-only ingress, and metadata egress match. Open setup wizard (F04), proxy IP (F25), recursive re-ownership (F32). |
| Traefik and ForwardAuth | ⚠️ | Ports, no dashboard, JSON logs, and header stripping match. Cluster-wide Secret access (F13), ACME DNS (F28), translated endpoint (F18), rotation (F03). |
| AmneziaWG | ✅ | Peer ACLs inside the pod. The outer egress policy is broad and relies on those ACLs. |
| DDNS | ⚠️ | Dedicated token. Does not reconcile record settings (F17). |
| Alloy | ⚠️ | Digest-pinned, read-only host mounts, ingestion-only credentials. Journal filter gaps (F24). |
| OpenObserve | ⚠️ | Version, local mode, retention, and limits match. Heartbeat alert (F06), incident model (F15), shared Secret (F35). |
| Zabbix | ⚠️ | Templates, dashboard, and internal mail match. Unauthenticated trapper (F22), default-credential window (F04), weak passwords (F23). |
| Intel GPU plugin | ✅ | Shared allocations, digest-pinned, in `kube-system`. |

## Broader risks

- **Backups:** RAIDZ1 survives one disk failure but not deletion, corruption, theft, or pool loss. The `backup` datasets only mark scope; nothing copies them off-host. Set up encrypted off-host backups and test a restore before storing important data.
- **Encryption key:** the ZFS key sits on the host for automatic unlock. It protects detached disks, not a stolen machine.
- **Host firewall:** the host accepts all traffic from the pod CIDR. A compromised pod, or a VPN peer routed through the AmneziaWG pod, can reach every host port unless the in-pod ACLs stop it.
- **Broad HTTPS egress:** Grist, OnlyOffice, OpenCloud, AFFiNE, and Immich may reach any public HTTPS address, which gives a compromised app an easy exfiltration path. Narrow it where a stable destination exists.
- **No admission baseline:** nothing enforces Pod Security Admission, so a future template can silently add privileges.
- **AppArmor relaxation:** `kernel.apparmor_restrict_unprivileged_unconfined=0` is set host-wide to work around a runtime issue.
- **Capacity:** memory requests are budgeted, but limits can burst together. PostgreSQL, indexing, ML inference, conversions, and imports can peak at the same time. Several OOM incidents are already recorded.
- **Self-monitoring:** alerts depend on the same host, cluster, database, and mail server they monitor. Add an independent external check.

## Documentation inconsistencies

- `NETWORKING.md` still describes external relay allowances for alerts; alerts now go directly to Stalwart TCP 2525.
- The Intel GPU README describes a future second consumer, but Immich and Jellyfin already share the GPU.
- `AGENTS.md` lists four installer modes; the installer also has `validate`.
- The live handoff's headline status predates its later entries. It also used a mock ACME server, so real certificate issuance has never been proven (see F28).

## Checked and not counted as issues

- Disabled `full_page_writes` and data checksums are deliberate ZFS tuning choices in PLAN.md.
- Anonymous SMTP on TCP 2525 is deliberate, and network policy restricts it to OpenObserve and Zabbix.
- Jellyfin falls back to CPU when the GPU stage is off.
- Stalwart's temporary recovery admin is removed after configuration.
- The Zabbix passive agent listens only on loopback.
- The media VPN default-deny blocks direct egress while `tun2socks` is starting.

## Recommended order

1. Fix the installation blockers: F01, F02, F08, and F07.
2. Fix certificate issuance (F28) and pod-to-edge routing (F18). Then prove both with a real Let's Encrypt run.
3. Close the administrator bootstrap window (F04) and enforce password rules (F23).
4. Separate the WOPI secret (F29), restrict WOPI hosts (F05), and narrow Traefik RBAC (F13).
5. Configure AFFiNE's public URL (F19) and fix the Grist identity issues, ideally by replacing the helper: F11, F20, F21, and F30.
6. Complete the rotations (F03), use Recreate for the ARR apps (F12), and fix Jellyfin `fsGroup` (F32).
7. Fix the heartbeat alert (F06) and define the incident model (F15).
8. Upgrade Stalwart (F14), give it a scoped search key (F31), and fix DDNS (F17).
9. Clean up hardening items: F22, F24, F25, F26, F33, F34, F35, and F36.
10. Set up backups, a tested restore, and external outage monitoring.
11. Run hardware and peak-load acceptance on the target host.

## Live acceptance still needed

All runs must use `sudo python3 ansible/install.py`.

- **Install:** a fresh create, an interrupted create with resume, a full reapply, and a reboot all succeed.
- **Certificates:** real Let's Encrypt issuance and renewal for Traefik and Stalwart.
- **Identity:** browser login, logout, and disabled-user behavior work in every OIDC application, from inside the consuming pods.
- **Bootstrap:** no remote client can claim administrator setup at any point.
- **Office:** OpenCloud documents open, edit, and save; a foreign WOPI host is rejected.
- **Media:** indexing, download, import, and playback work; VPN loss never leaks traffic.
- **Mail:** inbound forwarding, local delivery, authenticated relay, and rejection of unauthorized relay all work.
- **Alerts:** positive alerts, heartbeat absence, recovery, and reminders reach the mailbox.
- **Rotation:** every advertised rotation takes effect, and old credentials stop working.
- **Restore:** backups restore a consistent application and identity state.
