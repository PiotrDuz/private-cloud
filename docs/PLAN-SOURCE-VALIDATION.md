# PLAN.md source validation and amendment plan

Reviewed revision: `42cf21b` (`OIDC final`).
Method: nine parallel static audits of PLAN.md sections against roles, templates, scripts, catalog, and installer contract.
This review is static only and does not certify a deployment.
It supersedes [PLAN-IMPLEMENTATION-REVIEW.md](PLAN-IMPLEMENTATION-REVIEW.md), which reviewed `09da3c5` before the PLAN restructure and the Keycloak additions.
The companion [PLAN-HISTORY-REVIEW.md](PLAN-HISTORY-REVIEW.md) still applies.

## Findings summary

| Severity | Count | Headline |
| --- | --- | --- |
| P1 | 4 | Keycloak absent; Stalwart DNS token not injected; Grist unauthenticated; Jellyfin SSO policy contradiction |
| P2 | 13 | ARR storage classification; probe gaps; inbox confirmation; ML egress; VPN ACLs; OIDC-dependent glue; version risk |
| P3 | 36 | Wording, naming, documentation, and small enforcement gaps |

The dominant issue is the missing Keycloak subsystem.
PLAN.md defines it as the shared identity provider and makes eleven sections depend on it.
No role, installer stage, manifest, Secret, dataset, catalog entry, preflight assert, or documentation exists.
The second cluster is authentication wiring around Grist, Jellyfin, Stalwart, and Immich.
The third cluster is reconciliation work: ARR storage classification, probe coverage, and documentation drift.

## P1 findings

### P1-1: The Keycloak subsystem does not exist

PLAN.md:95-114 requires a deployed Keycloak in `private-cloud` with a dataset, database, realm, clients, and Traefik exposure.
Repository-wide search finds `keycloak` only inside PLAN.md.
There is no `ansible/roles/keycloak`, no `k0s-services/keycloak`, no stage in `install.py:198-200`, no entry in `install_helpers.py:224`, no preflight assert (`roles/preflight/tasks/main.yml:31`), no catalog row (`ansible/service_catalog.yml:6-30`), and no `site.yml` include.
No secret schema exists (`install_helpers.py:44-58`), and no example-config section exists (`config/private-cloud.example.yml:2-24`).

Blocked PLAN statements:

| PLAN lines | Dependent requirement |
| --- | --- |
| 95-114 | Keycloak deployment, realm, clients, redirect URIs, split-DNS issuer, logout, admin restriction |
| 131-133 | Stalwart OIDC directory, token audience validation, claim-to-mailbox mapping |
| 173 | OnlyOffice WOPI through a Keycloak-authenticated OpenCloud session |
| 183-186 | OpenCloud OIDC/PKCE, autoprovisioning, client registration, claim mapping |
| 201-204 | Grist forwarded-header auth through a Keycloak OIDC ForwardAuth helper |
| 227-229 | AFFiNE OIDC client and private-issuer egress |
| 255-258 | Immich native OIDC, redirects, backchannel logout |
| 322-325 | Jellyfin OIDC plugin, role mapping, Quick Connect |
| 346 | Keycloak as the shared identity source in Security |
| 366-372 | traefik-forward-auth helper, header passing, header stripping, allowlist |
| 381-382 | NetworkPolicies to Keycloak and backchannel logout |
| 386 | Keycloak placement in `private-cloud` |

Amendment options:
1. Implement the full Keycloak stage contract described in `AGENTS.md`: prompts, secrets schema, preflight asserts, example config, catalog, `site.yml`, namespace policies, and per-service clients.
2. Defer Keycloak explicitly by moving the section to TODO.md and marking dependent PLAN bullets as deferred.
Confidence: high.

### P1-2: Stalwart's Cloudflare DNS-01 token is stored but never injected

PLAN.md:138-139 requires DNS-01 certificate issuance with a dedicated Cloudflare token.
The token is written to the runtime Secret (`roles/stalwart/templates/runtime-secret.yml.j2:12`) and referenced by the plan (`roles/stalwart/templates/plan.ndjson.j2:4`).
The StatefulSet environment list (`k0s-services/stalwart/templates/statefulset.yaml.j2:41-54`) never exposes it, and the configuration Job (`configuration-job.yaml.j2:36-41`) does not either.
Certificate issuance and renewal fail when ACME resolves the environment variable reference.
Impact: SMTP STARTTLS and HTTPS for the mail hostname cannot obtain certificates.
Amendment: add a `secretKeyRef` environment entry for `STALWART_CLOUDFLARE_API_TOKEN` to the server and Job.
Confidence: high.

### P1-3: Grist is publicly reachable without authentication

PLAN.md:201-206 and 366-371 require Keycloak ForwardAuth for Grist.
No ForwardAuth helper, middleware, or `GRIST_FORWARD_AUTH_HEADER` exists anywhere; the strings appear only in PLAN.md.
Grist still serves its public Ingress (`k0s-services/grist/templates/ingress.yaml.j2:7-8`) with `GRIST_DEFAULT_EMAIL` set (`deployment.yaml.j2:43`), so unauthenticated visitors receive the configured default identity.
Impact: the deployed system does not meet the PLAN authentication contract, and the endpoint must be treated as open access until the helper exists.
Amendment: deploy the ForwardAuth chain, strip identity headers, set the forwarded header, or disable the public route until then.
Confidence: high.

### P1-4: The Jellyfin OIDC plugin is unpinned and actively disabled

PLAN.md:322 and 325 require a pinned OIDC plugin installed before Jellyfin starts.
Jellyfin is pinned to `10.11.4` (`ansible/roles/media/defaults/main.yml:6`), but no plugin version is pinned.
The pre-start helper disables the plugin repository (`media/jellyfin_helpers.py:9-13`) and every installed plugin (`:30-37`), so an installed plugin would be disabled at startup.
Upstream: plugin `1.0.7.0` targets Jellyfin 10.11; plugin `2.x` requires Jellyfin 12.
Amendment: pin plugin `1.0.7.0`, allow its manifest source, and exempt it from the disable pass; or amend PLAN to drop SSO.
Confidence: high.

## P2 findings

### P2-1: ARR and media-library datasets use backup instead of no-backup

PLAN.md:266-267 requires `tank/secure/no-backup/k0s/services/<service>` for Sonarr, Radarr, Prowlarr, qBittorrent, and the media library.
The catalog, role defaults, preflight asserts, and docs all use `backup`:
`ansible/service_catalog.yml:14-18`, `ansible/roles/media/defaults/main.yml:16-20`, `ansible/roles/preflight/tasks/main.yml:753-758`, `docs/NETWORKING.md:153`.
The media role additionally hard-codes qBittorrent paths under `backup` (`roles/media/tasks/main.yml:91,100`).
Impact: backup scope includes re-downloadable media, and the PLAN target is silently false.
Amendment: either switch all five datasets, host paths, preflight asserts, and docs to `no-backup`, or amend PLAN.md:266-267 to `backup` with a rationale.
Confidence: high.

### P2-2: Probe coverage does not meet the universal requirement

PLAN.md:412 requires readiness and liveness for every workload.
Missing both: Jellyfin (`k0s-services/jellyfin/templates/workloads.yaml.j2`), AmneziaWG (`networking/templates/amneziawg.yaml.j2`), the Intel GPU DaemonSet (`intel-gpu/templates/daemonset.yaml.j2`), and Cloudflare DDNS (`networking/templates/ddns.yaml.j2`).
Readiness only: Alloy (no liveness, `alloy/templates/deployment.yaml.j2:37-43`) and ARR app containers (`arr/templates/workloads.yaml.j2:201`).
Unprobed helper containers: ARR `dns`, `vpn-route`, and `file-logs` (`arr/templates/workloads.yaml.j2:72,160,214`).
Amendment: add the missing probes and exempt init containers, Jobs, and the DDNS CronJob in PLAN wording.
Confidence: high.

### P2-3: Destination-inbox alert confirmation is not implemented

PLAN.md:416 requires confirmation at the destination inbox.
The installer verifies heartbeat ingestion only (`roles/logging/tasks/main.yml:144`), and `TODO.md:32` tracks inbox verification as outstanding.
`k0s-services/zabbix/README.md:29` calls delivery an operator acceptance check.
Amendment: add a test-message and inbox assertion to the notifications stage, or demote the PLAN bullet to an operator acceptance step.
Confidence: high.

### P2-4: Immich machine learning cannot download models

`k0s-services/immich/README.md:15` states models download on demand.
The ML pods have no HTTPS egress rule, and the pod label list in `networking/templates/private-cloud-egress.yaml.j2:29` omits the ML workload.
Impact: face recognition fails after a model cache loss.
Amendment: add an explicit 443 egress rule for the ML pods, or pre-seed the model cache on the dataset.
Confidence: medium-high.

### P2-5: AmneziaWG peer ACLs do not use the configured cluster CIDRs

PLAN.md:400 requires denying peer access to pod and service CIDRs.
The pod firewall rejects hardcoded RFC1918 ranges only (`networking/templates/amneziawg-secret.yml.j2:32-38`) and then accepts the rest.
The configured `pod_cidr` and `service_cidr` are never injected into the peer rules.
Impact: non-RFC1918 cluster ranges would be reachable from approved peers.
Amendment: add explicit configured-CIDR rejects and validate containment.
Confidence: high on the code shape.

### P2-6: PLAN's "each ARR service" dataset wording is unsatisfiable

PLAN.md:264 defines the stack as Sonarr, Radarr, Prowlarr, qBittorrent, and OpenVPN.
PLAN.md:266 gives every ARR service a dataset and 10Ti PV.
The OpenVPN gateway is stateless and mounts only host, Secret, and ConfigMap volumes (`arr/templates/workloads.yaml.j2:86-89`); `storage.yaml.j2:1` creates no OpenVPN PV.
Amendment: scope the storage bullet to the persistent ARR applications and name the gateway as stateless.
Confidence: high.

### P2-7: Grist header stripping and single-team configuration are absent

PLAN.md:205-206 requires a single team site and removal of client-supplied identity headers.
No `GRIST_SINGLE_ORG` setting exists, and no Traefik header-stripping middleware exists.
Impact: adding ForwardAuth without stripping would create an identity-spoofing path.
Amendment: set the single-org setting and add a strip middleware ahead of the auth middleware.
Confidence: high.

### P2-8: The pinned Stalwart digest predates security fixes

`ansible/roles/stalwart/defaults/main.yml:18` pins `v0.16.21`.
The `v0.16` tag now resolves to `v0.16.22`, which includes STARTTLS session-state discards, partial-command discards, and an OIDC signing-key fix.
Impact: the pinned build lacks fixes that matter to PLAN's STARTTLS and OIDC requirements.
Amendment: bump the digest to `v0.16.22` and verify the runtime asserts.
Confidence: high.

### P2-9: traefik-forward-auth is effectively unmaintained

PLAN.md:366 names an unmaintained project.
Upstream discussion `thomseddon/traefik-forward-auth#379` documents the maintenance stop and recommends forks.
Amendment: choose a maintained forward-auth implementation or vendor one, and pin its image.
Confidence: high.

### P2-10: Prose documentation predates Keycloak and OIDC

`README.md:30-43`, `docs/NETWORKING.md:15-21`, `docs/OPERATIONS.md:3`, `docs/SETUP.md`, and `zabbix/ZABBIX.md` describe a system without OIDC, ForwardAuth, or a Keycloak host.
Amendment: refresh the docs when the Keycloak direction is decided.
Confidence: high.

### P2-11: ZABBIX.md points operators at the wrong configuration keys

`zabbix/ZABBIX.md:8` sends operators to `private_cloud.zabbix` for hostname and server settings.
The hostname is `networking.zabbix_hostname`, and the active server comes from `service_catalog.yml:3-4`.
Amendment: correct the documentation to the catalog and networking keys.
Confidence: high.

### P2-12: User-namespace write permissions are unverified

AFFiNE and Immich pre-create data directories owned by host `root:root 0750` (`roles/affine/tasks/main.yml:51-60`, `roles/immich/tasks/main.yml:86-92`).
Both containers run as root inside a user namespace (`hostUsers: false`).
Container root may see the directories as overflow and fail to write.
Amendment: verify on the live host, then chown with an init step, `fsGroup`, or idmapped mounts.
Confidence: medium.

### P2-13: The OnlyOffice WOPI secret chain is incomplete

PLAN.md:172-173 requires WOPI integration over authenticated sessions.
OnlyOffice enables JWT with its own credentials (`onlyoffice/templates/deployment.yaml.j2:37-43`).
The OpenCloud collaboration environment (`opencloud/templates/deployment.yaml.j2:93-101`) sets no shared WOPI or JWT secret.
Amendment: wire a shared secret from the OnlyOffice Secret into both workloads.
Confidence: medium-high.

## P3 findings

| # | PLAN ref | Finding | Evidence | Amendment |
| --- | --- | --- | --- | --- |
| 1 | 89-90 | Checksum and WAL wording lacks exact settings | `postgres/deployment.yaml.j2:43-50,73-74` | Name `data_checksums` and `wal_init_zero`/`wal_recycle` values |
| 2 | 56 | PLAN says "ZED mount caches"; code uses `zfs-list.cache` | `zfs/defaults/main.yml:11` | Align terminology |
| 3 | 56 | TODO.md still lists ZFS startup verification as outstanding | `TODO.md:9` | Close or restate the TODO item |
| 4 | 71 | Reapply does not verify `--enable-worker` or `--no-taints` | `k0s/tasks/main.yml:259-265` | Extend the service assert |
| 5 | 73 | Shared media library contradicts "single-writer workloads" | `arr/templates/workloads.yaml.j2:210-213` | Say "one replica per workload" |
| 6 | 68 | Secrets and Namespaces live in role templates, not `k0s-services` | `roles/postgres/tasks/main.yml:96`, `roles/k0s/templates/namespace.yml.j2:1` | Scope the bullet to public workload manifests |
| 7 | 76-77 | "Initially" and "all containers" are broader than enforcement | `logging/tasks/host.yml:19` | Bound the journal to the logging stage; scope limits to repository-managed containers |
| 8 | 184 | Double space in "autoprovisioning mode  with" | PLAN.md:184 | Fix the typo |
| 9 | 189 | OpenCloud ID cache uses `nats-js-kv`, not memory | `opencloud/deployment.yaml.j2:86,89` | Set memory or reword |
| 10 | 214 | Manticore query log is not forwarded to stdout | `manticore/deployment.yaml.j2:29-65` | Set `QUERY_LOG_TO_STDOUT=true` or drop the claim |
| 11 | 240 | Valkey object name is `immich-valkey`; owned by the Immich stage | `immich/templates/valkey-deployment.yaml.j2:4` | Rename or reword |
| 12 | 494 | Retention is configurable; PLAN states a fixed 14 days | `install_helpers.py:503` | Say "configurable, default 14 days" |
| 13 | 475 | Indexed label is `level`, PLAN says `severity` | `alloy/templates/configmap.yaml.j2:245` | Rename or reword |
| 14 | 470 | Journal keep list includes all `systemd.*` units | `alloy/templates/configmap.yaml.j2:80` | Narrow the regex or widen the PLAN list |
| 15 | 432 | Zabbix exposes dataset used/utilization, not size/quota | `zabbix/zabbix-zfs-template.yaml:1062,1078` | Add dependent items or reword |
| 16 | 450 | SMART low-health trigger depends on a stock template | `zabbix_server/defaults/main.yml:17` | Bundle a trigger or document the dependency |
| 17 | 506 | OpenObserve upstream recommends a cooldown above five minutes | external docs | Keep five minutes deliberately or raise it |
| 18 | 227-228 | AFFiNE OIDC is licence-gated beyond ten seats | external docs | State the limitation in PLAN |
| 19 | 230 | AFFiNE docs pair Manticore 10.1.0; repo pins 29.0.2 | `manticore/deployment.yaml.j2:31` | Validate the pairing before rollout |
| 20 | 324 | Plugin quick-connect link anchor is stale | external README | Update the link |
| 21 | 377 | Firewall also accepts ICMP and DHCP from untrusted sources | `private-cloud-firewall.nft.j2:31-33` | Restate documented exceptions |
| 22 | 333 | ARR containers start as root and drop via the entrypoint | `arr/templates/workloads.yaml.j2:192-208` | Carve out entrypoint privilege drops |
| 23 | 337 | ARR keeps CHOWN, SETUID, and DAC_OVERRIDE | `arr/templates/workloads.yaml.j2:207` | Document required startup capabilities |
| 24 | 341 | OpenObserve fsGroup does not match dataset ownership; OnlyOffice is never chowned | `openobserve/deployment.yaml.j2:18-20`, `logging/defaults/main.yml:4` | Align ownership at apply time |
| 25 | 348 | Alloy ingestion passcode uses the OpenObserve root identity | `openobserve/deployment.yaml.j2:46-47` | Create a dedicated ingestion user |
| 26 | 355 | DDNS updates only existing A records | `ddns-script.yaml.j2:48-53` | Create missing records or reword |
| 27 | 461 | qBittorrent password is missing from update and rotate flows | `install.py:387-448` | Add the secret to both flows |
| 28 | 456 | Preflight does not validate the dataset inventory despite AGENTS.md | `roles/preflight/tasks/main.yml:124-129` | Add catalog path/stage/quota asserts |
| 29 | — | Empty `k0s-services/grafana` and `k0s-services/loki` directories | filesystem | Remove them |
| 30 | — | Dead `configured_secret_markers()` in the installer | `install.py:477-492` | Remove it |
| 31 | 455-456 | `private-cloud-zabbix` and "Dataset capacity dashboard" are undefined | `service_catalog.yml:3` | Define both terms |
| 32 | 271 | Recreate strategy applies only to qBittorrent | `arr/templates/workloads.yaml.j2:119-121` | Name qBittorrent in PLAN |
| 33 | 311 | IPv6 disablement is implicit through IPv4-only configuration | `install_helpers.py:282` | Document the enforcement mechanism |
| 34 | 293 | Prowlarr operator access is undocumented | `docs/SETUP.md:11` | Add a port-forward instruction |
| 35 | 309 | Endpoint validation accepts IPv6 while templates append `/32` | `install_helpers.py:344`, `arr/network-policy.yaml.j2:31` | Require IPv4 |
| 36 | 429-455 | Zabbix agent 7.0 with server 7.4 | `zabbix_agent/tasks/main.yml:28` | Supported skew; note or align versions |

## Amendment plan

### Workstream A: Identity decision

1. Decide whether Keycloak is implemented now or deferred.
2. If implemented, add the stage per `AGENTS.md`: prompts, `SECRET_SCHEMAS`, preflight asserts, example config, catalog row, and `site.yml` include.
3. Add Keycloak manifests, realm and client Secrets, Traefik route, split-DNS handling, and namespace policies.
4. Add per-service OIDC wiring for Stalwart, OpenCloud, Grist, AFFiNE, Immich, and Jellyfin.
5. If deferred, move PLAN.md:95-114 to TODO.md and mark dependent bullets as deferred.
6. Pin the Keycloak image by digest.

### Workstream B: Mail and certificates

1. Inject `STALWART_CLOUDFLARE_API_TOKEN` into the Stalwart StatefulSet and configuration Job.
2. Bump the Stalwart digest to `v0.16.22`.
3. Add Stalwart `Directory` OIDC objects, audience validation, and claim mapping once Keycloak exists.
4. Add mailbox suspension and deletion handling or a documented runbook.
5. Add explicit filtering objects or soften PLAN.md:153.

### Workstream C: Authentication exposure

1. Deploy the forward-auth helper and strip incoming identity headers.
2. Set `GRIST_FORWARD_AUTH_HEADER`, the logout path, and the single-team setting.
3. Pin Jellyfin OIDC plugin `1.0.7.0`, allow its repository, and exempt it from the disable pass.
4. Wire the OnlyOffice and OpenCloud shared WOPI secret.
5. Replace or vendor `traefik-forward-auth` with a maintained project.

### Workstream D: Storage reconciliation

1. Choose the ARR classification: switch the repository to `no-backup` or amend PLAN.md:266-267 to `backup`.
2. Apply the choice to role defaults, catalog, preflight asserts, media host paths, and `docs/NETWORKING.md`.
3. Scope the ARR storage bullet to persistent applications and exempt the stateless gateway.

### Workstream E: Reliability

1. Add the missing probes to Jellyfin, AmneziaWG, the Intel GPU plugin, DDNS, Alloy, and ARR helpers.
2. Add a test-message and inbox verification to the notifications stage.
3. Add HTTPS egress for the Immich ML pods or pre-seed the model cache.
4. Inject configured `pod_cidr` and `service_cidr` into AmneziaWG peer rejects.
5. Verify user-namespace write permissions for AFFiNE and Immich on the live host.

### Workstream F: Documentation

1. Refresh README, NETWORKING, OPERATIONS, SETUP, and ZABBIX docs after workstream A.
2. Correct the configuration keys in `zabbix/ZABBIX.md`.
3. Document the Prowlarr access method and the IPv6 enforcement mechanism.

### Workstream G: Version and dependency hygiene

1. Validate the AFFiNE and Manticore version pairing before rollout.
2. State the AFFiNE OIDC seat limitation.
3. Keep digest pins for OpenObserve, Valkey, and tun2socks; document tag drift.
4. Align or note the Zabbix agent and server versions.

### Workstream H: PLAN wording corrections

1. Fix the typo at PLAN.md:184 and the stale plugin anchor at PLAN.md:324.
2. Align labels and terms: `severity` versus `level`, retention configurability, "single-writer", "ZED mount caches", "initially", and "all containers".
3. Define `private-cloud-zabbix` and "Dataset capacity dashboard".
4. Name the exact PostgreSQL tuning values.

### Workstream I: Repository hygiene

1. Validate the dataset catalog in preflight.
2. Add the qBittorrent password to the update and rotate flows.
3. Create missing DDNS records or reword PLAN.md:355.
4. Remove the empty Grafana and Loki directories and the dead installer code.

## Section coverage

| PLAN section | Status | Notes |
| --- | --- | --- |
| 1. ZFS storage | Implemented statically | Terminology and TODO wording findings |
| 2. k0s cluster | Implemented statically | Reapply drift check and wording findings |
| 3. PostgreSQL | Implemented statically | Tuning wording only |
| 4. Keycloak | Not implemented | P1-1 |
| 5. Meilisearch | Implemented statically | None |
| 6. Stalwart email | Partial | P1-2, P2-8; OIDC and lifecycle gaps |
| 7. Apache Tika | Implemented statically | None |
| 8. Bleve | Implemented as embedded storage | None |
| 9. OnlyOffice | Implemented statically | P2-13; log forwarding needs live proof |
| 10. OpenCloud | Partial | P1-1 blocks OIDC; ID cache wording |
| 11. Grist | Partial | P1-3, P2-7 |
| 12. Manticore Search | Implemented statically | Query-log note |
| 13. Redis for AFFiNE | Implemented statically | None |
| 14. AFFiNE | Partial | P1-1, P2-4; licence caveat |
| 15. Valkey for Immich | Implemented statically | Naming and ownership note |
| 16. Immich | Partial | P1-1; ML egress P2-4 |
| 17. ARR stack | Partial | P2-1, P2-2, P2-6; P3 items |
| 18. Jellyfin | Partial | P1-4, P2-2; integration wording |
| 19. Security | Mostly implemented | P1-1, P2-12; UID and ownership notes |
| 20. Networking | Mostly implemented | P1-1, P1-3, P2-5; firewall and DDNS notes |
| 21. Observability | Mostly implemented | P2-2, P2-3; label and journal notes |

## External validation results

| Claim | Verdict | Note |
| --- | --- | --- |
| k0s `v1.36.2+k0s.0` checksum | Confirmed | Exact asset hash matches |
| TensorChord `pg18-v1.1.1` digest | Confirmed | Digest equals upstream tag |
| OnlyOffice `9.4.0.1` and native log forwarding | Confirmed | Tag exists; entrypoint behavior verified upstream |
| OpenObserve `0.90.3` digest | Confirmed | Pinned digest still resolves after a tag re-push |
| Immich `v3.1.0` OIDC and backchannel logout | Confirmed | Redirects and endpoint real |
| Grist forwarded-header support | Confirmed | Feature real; repo wiring absent |
| AFFiNE OIDC | Confirmed with licence caveat | Free within ten seats |
| Jellyfin OIDC plugin | Contradicted in repo | Plugin exists; repo disables it and pins the wrong generation |
| Stalwart `v0.16` feature set | Confirmed | Pin is stale by one patch |
| `traefik-forward-auth` | Confirmed unmaintained | Upstream recommends forks |
| Intel GPU shared allocations | Confirmed | `-shared-dev-num` and `gpu.intel.com/i915` real |
| Manticore 29.0.2 with AFFiNE | Unverified | AFFiNE docs use 10.1.0 |
| PostgreSQL tuning reference | Confirmed | URL valid |
| inbox.eu relay settings | Confirmed | Host, port, and implicit TLS match |

## Live-only validation boundary

Static evidence cannot establish ZFS unlock and mount after reboot, k0s startup order, pod readiness on the target host, i915 allocation, certificate issuance, public and split DNS, firewall and VPN isolation, ARR and Jellyfin behavior, database extension loading, retention after elapsed time, hardware telemetry, OpenObserve outage recovery, or inbox receipt.
The repository has no local test or CI contract.
The supported verification path is `ansible/install.py` on a live host.
This review did not run the installer or deploy resources.
