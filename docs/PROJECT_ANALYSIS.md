# Private cloud project analysis

Review date: 6 October 2026.

Source baseline: `a4e6b580ac2ae493aeee6293c6f1d9f3148f7a26` (`Fixes and rearrangement`).

Supplement reviewed: [chatFindings.json](../chatFindings.json), on 6 October 2026.

## Assessment

The architecture is reasonably coherent, but the current source does not support a conclusion that every supported installation and lifecycle operation will work. There are installation blockers, incomplete credential rotations, an ineffective missing-heartbeat alert, and security gaps around initial administrator setup and the public office integration. These should be resolved before treating the project as ready for Internet exposure and important personal data.

Several useful protections are already implemented: encrypted ZFS storage, per-service quotas, fixed local volumes, separated public configuration and Vault secrets, explicit stage dependencies, many restrictive pod security settings, namespace network policies, verified identity headers for Grist, restricted mail relaying, and functional service validators. Their presence does not resolve the specific contradictions below.

The existing [live test handoff](LIVE_TEST_HANDOFF.md) explicitly records incomplete whole-system acceptance. It contains later progress after its initial snapshot, including successful partial runs and a reboot, but does not record a completed fresh installation followed by complete validation, reapplication, and another reboot. It is historical evidence rather than proof that this source baseline passes every acceptance condition.

## Scope and evidence

The review used [PLAN.md](../PLAN.md) as target state and [TODO.md](../TODO.md) as outstanding work. All 31 existing Markdown files were read, including repository instructions, service READMEs, networking and operations documentation, validation documentation, and the live handoff. The inventory appears at the end of this report.

The source review covered the installer and its helpers, preflight, every Ansible stage, shared dataset and manifest tasks, Kubernetes service templates, provisioning scripts, Zabbix collectors, and the validation flow. Upstream documentation and pinned-version source were consulted where application behavior determines whether a configuration is correct.

The exported conversation contains 160 entries, including 64 reasoning blocks. Its technical observations were extracted as audit candidates and checked against the current source; they were not treated as established facts. This supplement adds ten numbered findings, F18–F27, expands maintenance recommendations, and records rejected or unresolved claims in the reconciliation section. It reports conclusions and evidence rather than reproducing the conversation's internal deliberations or secret material.

Static syntax checks parsed 48 Python assets and 123 non-Jinja YAML files without errors. Parsing was performed in memory and did not execute the scripts. Jinja templates were inspected but were not all rendered into a complete installation configuration.

No installer, playbook, disk operation, deployment, credential rotation, or live outage exercise was run for this review. The findings identify source-level causes and expected consequences; they do not assert that a deployed host has already been compromised. No implementation changes accompany this report.

“Confirmed” below means the source contains the stated contradiction or omission. “Conditional” means the consequence depends on a supported configuration, lifecycle action, or external state. “Upstream” means the behavior was checked against the relevant upstream implementation or release information. Proposed acceptance checks are operator work through the supported installer and existing live validation approach, not a proposal to add a unit-test suite.

## Findings overview

| ID | Severity | Finding | Evidence classification |
| --- | --- | --- | --- |
| F01 | High | The ZFS collector rejects the installer configuration dataset. | Confirmed installation blocker. |
| F02 | High | Pool membership validation compares data partitions with whole disks. | Confirmed mismatch for normal whole-disk ZFS pools. |
| F03 | High | Three supported rotations do not reconcile running consumers correctly. | Confirmed lifecycle omissions. |
| F04 | High | Public routes can expose unclaimed or default administrator setup. | Confirmed exposure sequence and upstream setup behavior. |
| F05 | High | Public OnlyOffice WOPI lacks a trusted-integrator restriction. | Confirmed configuration omission and upstream behavior. |
| F06 | High | OpenObserve cannot deliver the configured empty-result heartbeat alert. | Confirmed pinned-version scheduler behavior. |
| F07 | High | Accepted custom cluster network values are not applied to k0s. | Confirmed conditional configuration failure. |
| F08 | High | A failed early create can become impossible to resume through the installer. | Confirmed conditional recovery gap. |
| F09 | Medium | Disabling stages skips management without decommissioning existing services. | Confirmed lifecycle omission. |
| F10 | Medium | Accepted configurations without networking conflict with global validation and isolation. | Confirmed conditional failure. |
| F11 | Medium | Grist logout returns through a protected route and can log the user back in. | Confirmed routing conflict and upstream behavior. |
| F12 | Medium | Three ARR applications can overlap writers during deployment updates. | Confirmed rollout configuration and conditional data risk. |
| F13 | High | Traefik can read Secrets across the whole cluster. | Confirmed privilege scope. |
| F14 | Medium | The pinned Stalwart release predates a relevant queue-quota fix. | Upstream availability risk. |
| F15 | Medium | Log alert suppression does not implement the full incident lifecycle in PLAN.md. | Confirmed intent mismatch. |
| F16 | Medium | The policy integrity validator checks names rather than effective specifications. | Confirmed validation gap. |
| F17 | Medium | DDNS does not correct proxy or TTL drift when the address already matches. | Confirmed conditional convergence failure. |
| F18 | High | Application and ForwardAuth egress omit Traefik's translated pod endpoint. | Confirmed omission; likely connectivity failure requiring live CNI verification. |
| F19 | High | AFFiNE's configured public hostname does not configure its canonical URL. | Confirmed omission and pinned-version defaults. |
| F20 | Medium | Grist retains its own identity session behind authentication on every route. | Confirmed mode mismatch; conditional identity divergence. |
| F21 | Medium | Grist's public API requires a browser authentication cookie. | Confirmed routing and pinned middleware behavior. |
| F22 | Medium | LAN-accessible Zabbix ingestion lacks cryptographic agent authentication. | Confirmed configuration; conditional monitoring-data impersonation. |
| F23 | Medium | Several public administrator passwords have no strength floor or default rejection. | Confirmed input-validation gap. |
| F24 | Medium | Alloy's journal filter excludes common host authentication events. | Confirmed filter coverage gap. |
| F25 | Medium | Jellyfin and Stalwart lack managed HTTP proxy identity configuration. | Confirmed omissions; conditional client-IP misclassification. |
| F26 | Low | Raw password fingerprints appear in readable pod annotations. | Confirmed disclosure of a guessing oracle for weak passwords. |
| F27 | Medium | The identity checker equates HTTP success with accepted callbacks. | Confirmed verification gap. |

Severity reflects the consequence when the affected stage or configuration is used. An application that is never enabled is not exposed by its template. High-severity operational findings can prevent recovery or conceal a monitoring failure without providing an attacker with direct access.

## Detailed findings

### F01 — The ZFS monitoring inventory is rejected by its own collector

**Evidence.** [service_catalog.yml](../ansible/service_catalog.yml) includes `installer-config` with dataset `tank/secure/backup/private-cloud-config`. [monitoring_dataset_inventory.yml](../ansible/tasks/monitoring_dataset_inventory.yml) includes entries for enabled stages without changing their dataset paths. The ZFS stage is part of a normal installation, so this entry reaches the generated monitoring inventory.

In [zabbix-zfs-collector.py](../zabbix/zabbix-zfs-collector.py), `load_inventory()` accepts only paths matching `tank/secure/(backup|no-backup)/k0s/...`. The configuration dataset is outside that subtree. The function raises an exception before either metrics or snapshot collection starts.

**Impact.** ZFS monitoring cannot collect any dataset results from this inventory. [Zabbix Agent validation](../ansible/roles/zabbix_agent/validation/main.yml) executes both collector modes and requires successful output, so an installation with the agent enabled fails at this stage. This is a deterministic contract mismatch, independent of actual disk health.

**Recommendation.** Extend the collector's allowed dataset contract to include the exact installer configuration dataset while retaining strict path validation. Keep the configuration dataset monitored. Make the catalog and collector share the same allowed hierarchy rather than maintaining incompatible assumptions.

**Acceptance.** The generated full inventory is accepted as the Zabbix user, both collector modes return valid results, and the configuration dataset appears in discovery and capacity monitoring.

### F02 — Pool membership validation confuses whole disks and ZFS partitions

**Evidence.** [storage_checks.py](../ansible/storage_checks.py), in `check_pool_layout()`, reads `zpool status -P -L`, resolves each reported device path, and compares it directly with resolved configured disk paths. Disk selection and safety validation deliberately require whole disks.

When OpenZFS creates a pool using whole disks, its on-disk data vdev normally uses the generated ZFS partition. Consequently, the reported full path can be `/dev/sdb1` while the selected disk resolves to `/dev/sdb`. Resolving a symlink does not convert a partition into its parent disk. The supported [OpenZFS 2.3 source](https://raw.githubusercontent.com/openzfs/zfs/zfs-2.3.0/lib/libzfs/libzfs_pool.c) preserves partition paths when full-path naming is requested.

**Impact.** An otherwise correct existing pool can fail the membership comparison during preflight. Reapply, update, rotate, and partial recovery paths that invoke this helper can stop before doing their intended work. This does not mean that the pool contains the wrong disks.

**Recommendation.** Compare stable whole-disk identities after obtaining each actual partition's parent through sysfs, `lsblk`, or structured vdev metadata. Preserve the exact RAIDZ1 topology and disk-membership checks. Simply removing the check would discard an important destructive-operation safeguard.

**Acceptance.** A newly created pool passes reapplication with the same selected disks, and a genuinely different disk selection still fails before mutation.

### F03 — Supported credential rotation is incomplete

**Evidence.** [install.py](../ansible/install.py), in `rotate_secrets()`, advertises `affine_database`, `cloudflare_acme`, and `grist_oidc_cookie`. Their consumers do not implement the complete corresponding lifecycle.

| Rotation | Source behavior | Consequence |
| --- | --- | --- |
| AFFiNE database password | [AFFiNE tasks](../ansible/roles/affine/tasks/main.yml) create the PostgreSQL role only when absent and apply the credentials Secret, but never alter an existing role's password. | The Secret and database diverge; new connections or restarted pods can fail while the old database password remains valid. |
| Cloudflare ACME token | [Traefik deployment](../k0s-services/networking/templates/traefik.yaml.j2) reads the token through an environment variable without a secret-derived pod-template checksum or a rotation-triggered rollout. | Existing Traefik processes retain the old token and can fail renewal after the provider revokes it. |
| Grist OIDC cookie secret | [ForwardAuth deployment](../k0s-services/networking/templates/forward-auth.yaml.j2) reads `SECRET` from a Secret without a corresponding rollout mechanism. | Existing processes continue using the old signing secret, so rotation does not immediately invalidate cookies. |

Kubernetes does not refresh an already running container's environment when a Secret object changes, as described in its [Secret distribution documentation](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/). For the database case, even an incidental deployment restart cannot fix the unchanged PostgreSQL role.

**Recommendation.** Reconcile the AFFiNE role password and ownership, update its Secret, and roll out consumers in a controlled sequence. Add checksums derived from the relevant secret values to the Traefik and ForwardAuth pod templates, or explicit change-triggered restarts. Verify both service recovery and rejection of old credentials where rejection is part of the rotation contract.

**Acceptance.** Each advertised rotation works without requiring an unrelated configuration change or a manual pod deletion. An AFFiNE database login succeeds using the new password and fails using the old one. Traefik uses the new ACME token, and ForwardAuth rejects cookies signed by the previous secret after rollout.

The installer explicitly rejects several other unsupported rotations, including some bootstrap administrator and identity credentials. Those restrictions are intentional and are not counted as this finding.

### F04 — Fresh public installations can expose administrator bootstrap

**Evidence.** [Immich ingress](../k0s-services/immich/templates/ingress.yaml.j2) publishes the application, while [Immich tasks](../ansible/roles/immich/tasks/main.yml) do not claim the first administrator or gate setup until that happens. OIDC auto-launch is not equivalent to disabling administrator signup. In pinned [Immich v3.1.0 authentication source](https://raw.githubusercontent.com/immich-app/immich/v3.1.0/server/src/services/auth.service.ts), administrator signup is allowed when setup is enabled and no administrator exists. Setup defaults to enabled in its [configuration repository](https://raw.githubusercontent.com/immich-app/immich/v3.1.0/server/src/repositories/config.repository.ts).

The same bootstrap concern exists for Jellyfin: [its workload template](../k0s-services/jellyfin/templates/workloads.yaml.j2) publishes the ingress, while the local configuration helper does not complete administrator creation. The documented [Jellyfin setup wizard](https://jellyfin.org/docs/general/post-install/setup-wizard/) includes choosing the administrator account.

The exported conversation prompted an additional check of AFFiNE. Its [ingress](../k0s-services/affine/templates/ingress.yaml.j2) is also published without administrator claiming or setup isolation. Pinned [AFFiNE's setup controller](https://raw.githubusercontent.com/toeverything/AFFiNE/v0.27.3/packages/backend/server/src/core/selfhost/controller.ts) marks `/api/setup/create-admin-user` public and grants the administrator feature while the server is uninitialized. Its [self-host guard](https://raw.githubusercontent.com/toeverything/AFFiNE/v0.27.3/packages/backend/server/src/core/selfhost/guard.ts) checks self-hosted mode rather than operator identity. Include AFFiNE in the same protected bootstrap sequence.

Zabbix has a shorter related window: its public workload resources are applied before [api_auth.yml](../ansible/roles/zabbix_server/tasks/api_auth.yml) authenticates with the initial `Admin` / `zabbix` credentials and changes the account to the configured credentials.

**Impact.** On a fresh installation with working public DNS and routing, another person can reach bootstrap before the operator completes it. Immich's first-administrator behavior makes this a concrete account-takeover opportunity. The risk is conditional on public reachability during setup; it is not evidence of takeover on an existing initialized installation.

**Recommendation.** Keep bootstrap reachable only through an operator-controlled path until administrator initialization succeeds. Use temporary source restrictions, local access, or a staged ingress. Publish the unrestricted route only after initialization and closure of setup endpoints. Reject known vendor-default administrator passwords where the installer accepts a replacement.

**Acceptance.** A remote unauthenticated client cannot claim administrator setup at any point in a fresh installation. The intended operator can complete setup, and the application retains the correct administrator after reapply and reboot.

### F05 — OnlyOffice WOPI is public without a trusted-host boundary

**Evidence.** [OnlyOffice deployment](../k0s-services/onlyoffice/templates/deployment.yaml.j2) enables WOPI and JWT, and [its ingress](../k0s-services/onlyoffice/templates/ingress.yaml.j2) exposes the service publicly. The repository does not configure a trusted WOPI integrator filter. The pinned [OnlyOffice server defaults](https://raw.githubusercontent.com/ONLYOFFICE/server/v9.4.0.1/Common/config/default.json) have permissive IP-filter rules. OnlyOffice's [WOPI documentation](https://api.onlyoffice.com/docs/docs-api/more-information/faq/using-wopi/) requires restricting access to trusted integrators.

JWT protection for the separate Docs API does not establish that every WOPI session originated from this OpenCloud installation. A caller can supply an attacker-controlled WOPI host and its own valid tokens for that host. The [application HTTPS egress policy](../k0s-services/networking/templates/private-cloud-egress.yaml.j2) permits public TCP 443 destinations, so that path is not limited to the intended integrator.

**Impact.** Unrelated callers can potentially use the public editor and its conversion resources, creating availability and resource-abuse risk. This finding does not demonstrate access to another user's OpenCloud documents or unrestricted access to internal networks. Existing network policies constrain those consequences.

**Recommendation.** Restrict WOPI destinations to the intended OpenCloud host using supported server filtering and explicit denial of other hosts. Preserve browser editor access and legitimate callbacks. A blanket allowlist of browser source IPs would break remote users and would not express the correct trust relationship. Retain network-layer restrictions as a second boundary.

OpenCloud also explicitly disables WOPI proof verification for this integration. That compatibility choice should be documented as a weaker callback-origin guarantee and revisited against the pinned releases; a valid file access token is still required.

**Acceptance.** A legitimate OpenCloud document can be opened, edited, saved, and reopened. An editor session pointing to an unrelated WOPI host is rejected before it consumes conversion resources.

### F06 — The missing-heartbeat alert evaluates an empty result that cannot be sent

**Evidence.** [openobserve_helpers.py](../ansible/roles/logging/files/openobserve_helpers.py) defines the heartbeat rule as a custom query filtering heartbeat records, with a row-count condition `< 1`. When no heartbeat exists, the matching record set is empty.

In the pinned OpenObserve 0.90.3 implementation, the [alert evaluator](https://raw.githubusercontent.com/openobserve/openobserve/v0.90.3/src/service/alerts/mod.rs) can return that empty set as a triggered result. However, the [scheduler notification path](https://raw.githubusercontent.com/openobserve/openobserve/v0.90.3/src/service/alerts/scheduler/handlers.rs) requires the returned data to be nonempty before sending a notification. The configured absence case therefore cannot produce the intended email.

**Impact.** Quiet loss of heartbeat collection can remain invisible. Existing validation that observes a present heartbeat and delivers a positive log alert does not exercise this absence path.

**Recommendation.** Use a supported aggregate query that returns a nonempty diagnostic row when the heartbeat count is zero, then alert on that row. Confirm the exact SQL and scheduler contract on 0.90.3. Alternatively, implement an independent freshness probe that treats absent query results as a failure rather than depending on matching log rows.

**Acceptance.** Suspend heartbeat production through a controlled live exercise, wait past the configured window, and verify the actual warning in the destination mailbox. Restore production and verify the intended recovery behavior.

### F07 — Public network configuration does not configure the cluster network

**Evidence.** The installer accepts custom pod CIDR, service CIDR, and cluster DNS values, and the helpers validate their shape and overlap. [k0s tasks](../ansible/roles/k0s/tasks/main.yml) generate configuration with `k0s config create`, then modify worker-profile settings. They do not apply the accepted values to the effective cluster network configuration.

Firewall rules, VPN restrictions, and DNS-related configuration nevertheless consume the public values. The generated k0s network can remain on its defaults while those consumers use another range. k0s exposes these network settings in its [configuration reference](https://docs.k0sproject.io/stable/configuration/).

**Impact.** A supported non-default configuration can break DNS and routing or apply restrictions to the wrong ranges. A default configuration may work, which hides the mismatch during an ordinary default-only installation.

**Recommendation.** Apply the configured network values before first cluster startup and verify the effective configuration and node allocation against them. On an existing cluster, reject unsupported changes to immutable network settings before writing new public state. This greenfield project does not need an automatic CIDR migration path.

**Acceptance.** A fresh installation using non-default, non-overlapping ranges has matching effective k0s settings, DNS service addresses, pod addresses, host rules, and VPN exclusions. An unsupported later CIDR change fails before mutation.

### F08 — Early create failure lacks a supported resume path

**Evidence.** [install.py](../ansible/install.py) calls `require_configuration_dataset()` as soon as `tank` exists, before selecting the lifecycle mode. It also rejects `create` when the pool already exists, and requires stored public configuration for update, reapply, and rotate.

There is an interval between creating the pool and persisting the configuration dataset and its files. A failure in that interval leaves a pool that the entrypoint cannot resume. Recovery branches in [the ZFS role](../ansible/roles/zfs/tasks/main.yml) cannot help if the entrypoint rejects the state before invoking the role. Runtime cleanup removes staged runtime material on failure.

**Impact.** A power failure or task error during early installation can require an undocumented manual intervention. Retrying the supported entrypoint cannot complete the partially created state, even when the selected disks and intended configuration are known.

**Recommendation.** Persist a protected create-intent record and the necessary recoverable configuration before destructive work. Allow a narrowly defined authenticated resume when the existing pool matches that intent. Resume must not erase disks again or adopt an arbitrary pool. Document recovery for each persistence boundary, including encryption-key availability.

**Acceptance.** An interrupted create can resume at the pool-created and encrypted-root-created boundaries using the supported entrypoint. An unrelated existing pool is still rejected.

### F09 — A disabled stage can leave a publicly reachable unmanaged service

**Evidence.** [site.yml](../ansible/site.yml) conditionally includes each role when its stage is enabled. Disabled stages have no corresponding stop or removal branch. Applying the current rendered resources also does not prune objects that disappear from a conditional template.

**Impact.** Changing a previously enabled stage to false can leave its Deployments, ingresses, Secrets, or host support services running. Its validation and monitoring inventory can then omit it. The configuration may suggest that a service is disabled while it remains externally reachable.

**Recommendation.** Define stage-disable semantics explicitly. Either reconcile the stopped and unpublished state while preserving datasets, or reject disablement of an installed stage until an explicit decommission procedure has completed. Avoid deleting user data as a side effect of a boolean setting.

**Acceptance.** Disabling an installed service removes public access and stops its execution, or fails with a documented actionable requirement. Retained data remains recoverable and the monitoring view represents the retained state accurately.

### F10 — Networking is optional in the catalog but required by global assumptions

**Evidence.** [service_catalog.yml](../ansible/service_catalog.yml) allows several infrastructure stages with only k0s as a dependency. A configuration with k0s enabled and networking disabled can therefore be accepted.

[cluster.yml](../ansible/validation/cluster.yml) runs the production-integrity checker whenever k0s is enabled. [check_production_integrity.py](../ansible/validation/check_production_integrity.py) unconditionally loads the edge `traefik-dynamic` ConfigMap. That object is absent if the networking stage has never run. In addition, namespace default-deny resources belong to [the networking stage](../k0s-services/networking/templates/default-deny.yaml.j2), rather than baseline namespace creation.

**Impact.** An accepted stage combination can fail global validation and omit the baseline isolation promised by PLAN.md. Service-specific policies may still impose some restrictions, but they do not make this contract consistent.

**Recommendation.** Put baseline namespace isolation in the cluster stage and condition edge-specific validation on the edge stage, or require networking for every supported workload configuration. Choose one supported model and make installer, catalog, preflight, and validation agree.

**Acceptance.** Every accepted stage combination has a complete validation path and the intended default-deny baseline.

### F11 — Grist's signed-out route is protected by the login middleware

**Evidence.** [ForwardAuth configuration](../k0s-services/networking/templates/forward-auth.yaml.j2) sends logout to `https://<grist>/signed-out`. [Grist ingress](../k0s-services/grist/templates/ingress.yaml.j2) applies ForwardAuth to the entire `/` prefix, including this route. The pinned [ForwardAuth logout handler](https://raw.githubusercontent.com/thomseddon/traefik-forward-auth/v2.2.0/internal/server.go) clears its cookie and redirects to the configured destination.

**Impact.** The destination immediately requires authentication again. With an active OpenCloud SSO session, the browser can silently log back in; without one, it returns to login. This conflicts with the explicit target of logout without redirect loops.

**Recommendation.** Provide a narrowly scoped unprotected signed-out page or another supported terminal logout route. Preserve identity-header stripping on authenticated application routes. Provider-wide logout should be used only when the configured discovery and application flow support it.

**Acceptance.** Logout terminates on a stable signed-out page, protected Grist documents remain inaccessible without reauthentication, and forged identity headers remain ineffective.

### F12 — ARR singleton databases use a rollout that permits overlapping pods

**Evidence.** [ARR workloads](../k0s-services/arr/templates/workloads.yaml.j2) use `Recreate` for qBittorrent, but Sonarr, Radarr, and Prowlarr inherit the default Deployment rolling strategy. Each application has one replica and its own persistent configuration volume.

During an update, old and new pods can coexist. `ReadWriteOnce` does not prohibit two pods on the same node from mounting the volume; the [Kubernetes access-mode documentation](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#access-modes) defines it at node scope.

**Impact.** Two application processes can touch the same singleton SQLite/configuration state during rollout. Database locks, startup failures, and data consistency problems are possible. Corruption was not demonstrated by this audit.

**Recommendation.** Use `Recreate` for these singleton stateful applications, or another strategy that explicitly guarantees one writer. A short maintenance interruption is appropriate for this single-host design.

**Acceptance.** An application image or configuration update never starts a second writer before the old process has stopped, and retained application state opens successfully afterward.

### F13 — Internet-facing Traefik has cluster-wide Secret read access

**Evidence.** [traefik-rbac.yaml.j2](../k0s-services/networking/templates/traefik-rbac.yaml.j2) grants `get`, `list`, and `watch` for Secrets in a ClusterRole and binds that role to Traefik globally. Namespace restrictions in Traefik provider configuration do not narrow API authorization.

**Impact.** Compromise of the edge process or its service-account token permits reading application credentials in other namespaces, increasing the impact of an edge vulnerability. Secret contents are sensitive even when applications otherwise have strict network policies.

**Recommendation.** Determine the actual informer permissions required by the pinned Traefik release. Use namespace-scoped Roles and bindings for namespaced resources, narrow Secret access wherever supported, and retain only genuinely cluster-scoped discovery permissions separately. Kubernetes documents this approach in [RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

**Acceptance.** The edge service still discovers every supported ingress, while its service account cannot read unrelated application credentials. Check API authorization as well as configured provider namespaces.

### F14 — Stalwart's pinned release has a relevant upstream availability defect

**Evidence.** [Stalwart defaults](../ansible/roles/stalwart/defaults/main.yml) pin `stalwartlabs/stalwart:v0.16` at digest `sha256:388dcb75a70727c5b551249a6d34b1f1321294852489e4fa3a4e6be698b7c4f0`. Image metadata checked during the review identifies this as 0.16.22.

The [Stalwart 0.16.25 release notes](https://github.com/stalwartlabs/stalwart/releases/tag/v0.16.25), published 5 October 2026, fix unenforced MTA queue quotas with an empty match expression, including the global quota created on first startup. They also describe DKIM management fixes relevant to automatic DNS operation.

**Impact.** Mail load can exceed the expected queue protection on the pinned release. A ZFS quota eventually bounds some file storage, but it does not substitute for a working mail queue quota, especially with metadata in shared PostgreSQL. This is an availability concern, not a finding that Stalwart is an open relay.

**Recommendation.** Review and adopt a verified patch release and digest containing the fixes. Explicitly inspect effective queue limits and DKIM behavior instead of relying on first-start defaults. Keep the release change controlled and validate native login, inbound delivery, relay restrictions, alert delivery, and DNS management afterward.

**Acceptance.** Effective queue quotas are enforced under a bounded mail-load exercise, and local mail plus authorized outbound relay operation remain functional.

### F15 — Log rules do not implement stateful problem and recovery handling

**Evidence.** PLAN.md requires suppression while a problem stays open, recovery emails, and recurring reminders. [openobserve_helpers.py](../ansible/roles/logging/files/openobserve_helpers.py) creates severity rules over a five-minute window with sixty-minute silence. The definitions do not identify a persistent problem per service, model a recovery transition, or retain an open incident after matching rows leave the window.

**Impact.** A single error followed by silence ages out without recurring reminders. Multiple unrelated services can share one rule's suppression window. Silence is a delivery throttle, not proof of incident deduplication or recovery. The explicit four-rule OpenObserve design and the broader system-wide requirement need reconciliation.

OpenObserve's internal logs are excluded from severity rules to prevent feedback loops. That is understandable, but current health checks focus on Alloy endpoints and certificates; healthy ingestion alone does not prove that the OpenObserve query scheduler or SMTP delivery is functioning. F06 further weakens the missing-telemetry guarantee.

Certificate checks are also installed and validated under the logging-stage condition in [Zabbix Agent tasks](../ansible/roles/zabbix_agent/tasks/main.yml) and [validation](../ansible/roles/zabbix_agent/validation/main.yml). Certificate monitoring is useful even when centralized logging is disabled.

**Recommendation.** Either narrow the stated log-alert contract to event notifications with rule-level throttling or implement explicit incident identities, recoveries, and reminders. Add an independent check of the query and notification path. Separate certificate probing from optional log collection.

**Acceptance.** Two distinct service problems produce the intended notifications, an unresolved problem receives the intended reminder, and recovery generates the documented result. A broken query scheduler or SMTP path is detected independently of positive ingestion health.

### F16 — NetworkPolicy integrity checks do not validate the protection itself

**Evidence.** [check_production_integrity.py](../ansible/validation/check_production_integrity.py) asks [integrity_helpers.py](../ansible/validation/integrity_helpers.py) for repository policy names and rejects policies whose name is outside that set. It does not compare namespace and rendered policy specifications, and it does not require all expected policies to exist.

**Impact.** A deleted default-deny policy or an allow-all policy retaining a recognized name can pass this check. The validator detects some unmanaged additions, but cannot substantiate the effective network boundaries. An administrator able to change policies already has powerful access; the practical concern is unnoticed drift or accidental weakening.

**Recommendation.** Compare canonical rendered policy specifications keyed by namespace and name for enabled stages, and require mandatory policies to exist. Keep live allowed-and-denied traffic checks for semantics that a manifest comparison cannot prove.

**Acceptance.** A missing baseline policy and a modified known policy both fail validation, while the correct enabled-stage policy set passes.

### F17 — DDNS only reconciles address content

**Evidence.** [ddns-script.yaml.j2](../k0s-services/networking/templates/ddns-script.yaml.j2) creates and updates records with `proxied: false` and TTL 300. However, an existing record is updated only when its `content` differs from the discovered address.

**Impact.** A record with the correct IP but an incorrect proxy setting or TTL is left unchanged. For mail-related names, unintended Cloudflare proxying can prevent the intended direct SMTP routing. Public DNS validation may report the problem, but periodic DDNS execution does not correct its cause.

**Recommendation.** Compare and reconcile every owned record attribute, including content, proxy status, and TTL. Continue refusing ambiguous duplicate records.

The exported conversation also identified missing validation before mutation: `discover_address()` accepts any syntactically valid IPv4 address rather than requiring a globally routable address. The later public-DNS validator checks public address suitability, but that occurs after DDNS can publish the value. Reject non-global discovered addresses before changing records and retain the last valid published value when discovery is unusable.

**Acceptance.** A pre-existing proxied record with the current IP converges to the intended unproxied state on the next DDNS run.

### F18 — Pod-to-Traefik egress omits the translated endpoint

**Evidence.** [Traefik](../k0s-services/networking/templates/traefik.yaml.j2) maps host TCP 443 to pod TCP 8443. The `application-traefik-egress` and `opencloud-issuer-egress` policies in [private-cloud-egress.yaml.j2](../k0s-services/networking/templates/private-cloud-egress.yaml.j2) allow only the configured node address on TCP 443. [ForwardAuth](../k0s-services/networking/templates/forward-auth.yaml.j2) has the same endpoint allowance. These clients lack an egress exception to the `edge` namespace's Traefik pod on TCP 8443.

The repository already recognizes this translation in [AmneziaWG's policy](../k0s-services/networking/templates/amneziawg.yaml.j2): its comment explicitly describes HostPort DNAT and adds the Traefik pod selector with TCP 8443. The equivalent exception is absent for application identity and WOPI clients. General public TCP 443 allowances do not express the translated pod endpoint.

**Impact and confidence.** This is a likely blocker for issuer discovery, OAuth exchanges, and office callbacks under the repository's documented hostPort path. The exact result depends on when the installed network implementation evaluates policy relative to translation; [Kubernetes documents that ordering as implementation-dependent](https://kubernetes.io/docs/concepts/services-networking/network-policies/). It is therefore a supported concern, not proof that every deployed client currently fails. Host-origin validation cannot settle pod-origin reachability.

**Recommendation.** Add narrowly selected egress to Traefik TCP 8443 for the clients that require it, following the existing AmneziaWG pattern. Preserve the public HTTPS hostname, certificate validation, and default-deny policies. Wait for ForwardAuth readiness after its issuer becomes available; initial issuer unavailability should not be mistaken for a permanently successful networking stage.

**Acceptance.** Each affected pod can retrieve the configured HTTPS discovery document and complete its relevant token exchange or WOPI callback while unrelated edge ports remain denied.

### F19 — AFFiNE has no managed public canonical URL

**Evidence.** [AFFiNE's deployment](../k0s-services/affine/templates/deployment.yaml.j2) configures database, Redis, and search settings, but not `AFFINE_SERVER_EXTERNAL_URL`, `AFFINE_SERVER_HOST`, or HTTPS origin settings. Its role does not otherwise reconcile the canonical server URL to `private_cloud.affine.hostname`.

Pinned [AFFiNE 0.27.3 configuration](https://raw.githubusercontent.com/toeverything/AFFiNE/v0.27.3/packages/backend/server/src/core/config/config.ts) defaults to an empty external URL, host `localhost`, HTTP, and port 3010. Its [URL helper](https://raw.githubusercontent.com/toeverything/AFFiNE/v0.27.3/packages/backend/server/src/base/helpers/url.ts) derives the origin from those settings, and its [CORS implementation](https://raw.githubusercontent.com/toeverything/AFFiNE/v0.27.3/packages/backend/server/src/base/cors.ts) uses configured allowed origins.

**Impact.** A fresh deployment can advertise `http://localhost:3010`, generate unsuitable external links or OAuth URLs, and reject the intended browser origin. An `/info` response does not prove that browser mutations or OAuth work. An operator's stored application override can conceal the omission on an existing installation.

**Recommendation.** Configure the supported external URL as `https://` plus the installer hostname before application startup and check its effective value. The documented manual entry of AFFiNE's OIDC client secret is a separate supported setup step; its existence does not repair the missing canonical URL.

**Acceptance.** The fresh installation generates the intended external URLs, accepts authenticated browser mutations from its public origin, and completes the configured OAuth callback.

### F20 — Grist mixes session identity with authentication on every route

**Evidence.** [Grist's deployment](../k0s-services/grist/templates/deployment.yaml.j2) sets `GRIST_FORWARD_AUTH_HEADER` and the logout path, but leaves `GRIST_IGNORE_SESSION` unset. Its [ingress](../k0s-services/grist/templates/ingress.yaml.j2) applies ForwardAuth to every path. Pinned [Grist 1.7.16](https://raw.githubusercontent.com/gristlabs/grist-core/v1.7.16/app/server/lib/ForwardAuthLogin.ts) distinguishes session mode, which consumes the identity header at login, from all-request header mode, which requires `GRIST_IGNORE_SESSION=true`.

**Impact.** Grist's retained session and the independently authenticated proxy identity can disagree. For example, an existing Grist session for one identity can remain after the proxy authenticates another identity in the same browser. The exact browser sequence needs live acceptance; the missing coordination is visible in source. This also complicates logout and account suspension beyond F11.

**Recommendation.** Choose one coherent mode. All-route verified-header authentication should use the supported session-ignore setting; session mode should protect the login/logout paths and explicitly coordinate session expiry. Preserve stripping of caller-supplied identity headers in either design.

**Acceptance.** Reauthentication as a different user never retains the previous user's document access, and logout and suspension meet the chosen session contract.

### F21 — Grist API keys cannot independently authenticate through its public route

**Evidence.** The same all-path [Grist ingress](../k0s-services/grist/templates/ingress.yaml.j2) also protects `/api/`. Pinned [ForwardAuth 2.2.0](https://raw.githubusercontent.com/thomseddon/traefik-forward-auth/v2.2.0/internal/server.go) authenticates its own browser cookie before forwarding requests; it does not validate Grist API bearer tokens.

**Impact.** A native API client with a valid Grist API key but no ForwardAuth cookie receives an authentication redirect rather than normal Grist API handling. This limits integrations and contradicts an expectation that native application API authentication is sufficient. Browser access can still work, so this is a functional limitation rather than an anonymous API bypass.

**Recommendation.** Decide whether native API clients are supported and document the result. If they are, provide a route that delegates API authentication to Grist while stripping every trusted identity header; application authorization must remain enforced. Coordinate this with F20 rather than adding an unrestricted bypass or assuming all Grist editions support a replacement identity architecture.

**Acceptance.** A valid native API credential works without a browser cookie, while missing credentials and forged identity headers cannot grant protected document access.

### F22 — Zabbix accepts monitoring traffic without authenticated transport

**Evidence.** [Managed agent settings](../ansible/roles/zabbix_agent/templates/managed-settings.j2) set `TLSConnect=unencrypted` and `TLSAccept=unencrypted`. [Host provisioning](../ansible/roles/zabbix_server/tasks/api_hosts.yml) explicitly enforces `tls_accept: 1` and `tls_connect: 1`, the [Zabbix values for unencrypted connections](https://www.zabbix.com/documentation/7.4/en/manual/api/reference/host/object). The [server Service](../k0s-services/zabbix/templates/server-service.yaml.j2) exposes NodePort 31051, which the host and pod rules allow from configured local networks.

**Impact.** A permitted LAN client can reach the monitoring receiver without proving possession of a per-agent secret or certificate. Knowing the configured active host and item names can enable attempts to impersonate active-agent submissions and mislead monitoring. The exact accepted submission and its effects need a controlled live check. This is not exposure of the passive agent's port 10050: that listener is explicitly bound to loopback.

**Recommendation.** Authenticate active-agent transport with a dedicated PSK or certificates and reconcile both the server host object and agent settings. Store the credential in Vault and update all configuration-contract sites together. Reduce NodePort reachability where the intended local-agent path permits it.

**Acceptance.** The real agent reports successfully with authenticated transport, and a LAN client lacking its credential cannot submit accepted monitoring data for that host.

### F23 — Public administrator passwords can be trivially weak

**Evidence.** [Secret validation](../ansible/install_helpers.py), in `validate_secrets_configuration()`, checks all required strings for presence and applies additional length rules to selected secrets. OpenCloud, Stalwart, and Zabbix administrator passwords do not receive an equivalent strength floor or known-default rejection. Preflight does not add that restriction. [Zabbix authentication provisioning](../ansible/roles/zabbix_server/tasks/api_auth.yml) can accept already-working configured credentials, including the vendor default when supplied as the desired password.

**Impact.** The supported installer can publish native login or administrator endpoints with a one-character password or a known default. Correct operator input avoids this, but the otherwise strict configuration contract does not enforce it. OpenObserve's separately enforced 32-character administrator password is not part of this omission.

**Recommendation.** Offer generated high-entropy passwords, enforce a reasonable length floor, and reject known vendor defaults for publicly reachable administration. Avoid claiming that length alone proves entropy. Consider MFA or restricted administrative access where compatible with the intended public application routes.

**Acceptance.** The installer rejects trivial and known-default administrator passwords before deployment, while generated credentials pass and work after reapply.

### F24 — Central journal collection omits important authentication events

**Evidence.** [Alloy's journal relabeling](../k0s-services/alloy/templates/configmap.yaml.j2) retains selected systemd units, kernel transport, and private-cloud Zabbix identifiers. It does not explicitly retain `sudo`, `su`, or `login` identifiers, authentication facilities, or `private-cloud-firewall.service`. Records under ordinary `session-*.scope` units with these identifiers fail the current keep expression.

**Impact.** Common privilege-escalation and local authentication events can remain only in the host journal and disappear under local retention without entering the central audit/search stream. This is selective loss, not absence of all security logging: SSH-unit records and kernel events are already retained.

**Recommendation.** Include relevant authentication identifiers or verified authentication-facility fields, plus the managed firewall unit. Confirm actual fields on the supported distribution and retain bounded labels and redaction.

**Acceptance.** A controlled sudo event and a managed-firewall failure appear in OpenObserve with useful host, service, and severity context.

### F25 — HTTP applications do not receive a managed client-IP trust configuration

**Evidence.** [Jellyfin configuration](../ansible/roles/media/files/jellyfin_helpers.py) does not configure known proxies or local network classification. Its backend receives connections from Traefik. [Jellyfin's documentation](https://jellyfin.org/docs/general/post-install/networking/) states that reverse-proxy external-access controls require correctly configured known proxies.

The [Stalwart configuration plan](../ansible/roles/stalwart/templates/plan.ndjson.j2) likewise does not set HTTP `useXForwarded`. Its HTTP listener is separate from the SMTP listener's PROXY-protocol setup. [Stalwart's HTTP guidance](https://stalw.art/docs/http/settings/) requires explicit forwarded-IP handling behind a trusted proxy and warns against trusting such headers from arbitrary clients.

**Impact.** Remote clients can be recorded or classified as the proxy address. Jellyfin's per-user remote-access decisions and remote streaming limits can become unreliable; Stalwart's IP-based HTTP audit and abuse controls can lose client attribution. This does not prove an authentication bypass or that a deployed host has already banned its proxy.

**Recommendation.** Configure the application's supported trusted-proxy behavior and effective local ranges. Limit backend access to trusted proxy and necessary provisioning paths, preserve header sanitization, and avoid treating the entire pod CIDR as an identity authority.

**Acceptance.** LAN and remote requests are classified correctly, logs retain the intended client address, and caller-supplied forwarding headers cannot override that address through an untrusted path.

### F26 — Pod annotations expose raw password fingerprints

**Evidence.** [ARR workload annotations](../k0s-services/arr/templates/workloads.yaml.j2) include `checksum/qbittorrent-credentials`, the direct SHA-256 hash of the qBittorrent password. [Alloy's RBAC](../k0s-services/alloy/templates/rbac.yaml.j2) permits cluster-wide pod reads, exposing annotations without granting Secret reads.

**Impact.** A metadata reader gains an offline password-guess verification oracle when an operator chooses a predictable password. The enforced minimum length does not ensure random generation. Other multi-secret checksums should be reviewed, but knowing their combined hash does not automatically permit independent cracking of each unknown component. This finding is not disclosure of the plaintext password.

**Recommendation.** Prefer generated secrets and a rollout revision that does not publish their raw hashes, or use a keyed HMAC whose key is unavailable to metadata readers. A public salt alone would still permit offline guessing. Retain a reliable restart trigger when the authoritative secret changes.

**Acceptance.** Changed credentials still roll out the consumer, while pod metadata no longer provides a directly verifiable hash of a low-entropy password.

### F27 — Identity validation overstates what its HTTP checks establish

**Evidence.** [check_identity.py](../ansible/validation/check_identity.py) sends authorization requests and appends a client to `accepted_clients` whenever the status is 200, 302, or 303. It does not inspect the response body, redirect location, or OAuth error parameters. Its [HTTP helper](../ansible/validation/http_helpers.py) returns status and body without response headers.

**Impact.** An error page with HTTP 200 or an OAuth error redirect can satisfy the status-only condition. The current check proves discovery shape and limited authorization-endpoint responsiveness; it does not prove callback registration, successful login, token exchange, or claims. It also runs from the host and cannot disprove F18's pod-origin routing concern.

**Recommendation.** Inspect protocol-level errors and redirect destinations, include an intentionally invalid callback as a negative control in the existing live validator, and describe successful output narrowly. Verify issuer access from consuming pods and complete real browser OAuth flows separately.

**Acceptance.** A rejected callback fails verification even when returned as an HTTP success or redirect, while valid configured clients complete the supported identity flow.

## Service-by-service review

The following entries describe the current implementation and its remaining acceptance boundary. A row without a numbered finding means no additional concrete blocker was identified in that component, not that its entire dependency chain has been proven secure.

| Service or component | Assessment and improvement |
| --- | --- |
| OpenZFS storage | Encryption, fixed hierarchy, quotas, disk guards, scrub scheduling, and mount dependencies support the intended architecture; F01, F02, and F08 prevent confidence in monitoring and recovery lifecycles. |
| k0s | Version and checksum are pinned and the node/network-provider checks are useful; reconcile effective CIDRs under F07 and supported stage combinations under F10. |
| Traefik | HTTPS ingress, disabled dashboard, unknown-host routing behavior, and identity-header middleware fit the plan; address bootstrap exposure, token rotation, and excessive Secret permissions under F03, F04, and F13. |
| Grist ForwardAuth | Separate OIDC client and identity-header stripping are appropriate; F03, F11, F18, F20, and F21 cover rotation, logout, issuer reachability, session identity, and native API limitations. |
| Cloudflare DDNS | Separate API credentials and duplicate-record rejection are useful; complete reconciliation under F17 and retain appropriately scoped provider tokens. |
| AmneziaWG | Peer keys, namespace-local routing/NAT, and destination ACLs express the intended boundaries; verify actual LAN/DNS allowlists and denied pod/service/peer traffic on the host. |
| Intel GPU plugin | Infrastructure-level access to device paths is expected for the device plugin; verify the actual firmware, render-group membership, and two advertised allocations on supported hardware. |
| PostgreSQL | Separate application roles and database checks are useful; AFFiNE omits the reconciliation performed for several peers, and a shared server remains a common availability and backup dependency. |
| Meilisearch | A dedicated dataset and master-key Secret fit the plan; keep access limited to intended clients and validate key rotation with search operations rather than health alone. |
| Apache Tika | Private text extraction and resource limits are appropriate; exercise representative large or complex documents because malformed document processing is a resource-risk boundary. |
| Bleve | This role provisions storage used by OpenCloud rather than a standalone search server; its acceptance is successful OpenCloud indexing and search with durable index state. |
| OnlyOffice | Persistent state and TLS validation are present; F05 requires a trusted WOPI host boundary and F18 requires pod-origin callback reachability. |
| OpenCloud | Embedded identity configuration, registered application clients, and file-operation validation are substantial implementation; completed SSO flows, disabled-user behavior, WOPI editing, and consistent file/identity backup still need evidence. |
| Grist | Dedicated credentials and PostgreSQL support the intended service; reconcile session/header identity under F20 and explicitly support or exclude native API clients under F21. |
| Manticore | Dedicated storage and private application connectivity fit the intended AFFiNE search dependency; the live handoff records memory-pressure sensitivity during initial indexing. |
| Redis for AFFiNE | Private in-memory cache is intentional; disabled persistence means queued or transient state can disappear, so document which jobs are recreated after restart. |
| AFFiNE | Database preparation and private dependencies are implemented; complete rotation under F03, protect bootstrap under F04, and configure the public origin under F19. |
| Immich server | Database, identity, cache, and configuration support are implemented; protect first-administrator setup under F04 and verify actual uploads, account linking, and OAuth callback completion. |
| Immich machine learning | Writable model caches and a dedicated inference validator address earlier trial failures; prove model download, real inference, and sustained operation within the selected CPU/GPU memory budget. |
| Immich Valkey | Private ephemeral state is consistent with its intended cache/queue role; verify restart recovery and avoid an eviction policy that silently drops required job state. |
| Sonarr | Private media API and scoped storage mounts support the plan; F12 requires one database writer during updates, and full indexer/download/import operation is still an integration acceptance condition. |
| Radarr | The same rollout concern applies; verify configured quality profiles and completed imports rather than only saved API configuration. |
| Prowlarr | Indexer integration and synchronization depend on actual provider availability and credentials; F12 applies, and the network exception matrix can be narrowed to actual peers and ports. |
| qBittorrent | Explicit Recreate, tun0 binding, API provisioning, and restricted egress are useful protections; verify downloads and routing during gateway loss and recovery, including fresh starts. |
| OpenVPN gateway | Existing namespace policies and gateway restrictions support fail-closed routing; the historical handoff records recovery failures, so bounded tunnel-loss and server-outage acceptance remains essential. |
| tun2socks route helper | Application networking depends on route readiness; use an explicit startup-order/readiness contract to avoid transient availability failures before routes are ready. |
| Media DNS helper | DNS must remain within the VPN path for guarded applications; exercise both UDP and TCP DNS during startup and outage recovery. |
| Shared media library | Disposable backup scope is explicit and Jellyfin's mount is read-only; verify import ownership and quota exhaustion behavior without granting unrelated applications write access. |
| Jellyfin | Recreate and read-only library mounting are appropriate; protect the initial wizard under F04 and configure proxy/client classification under F25. |
| Grafana Alloy | Ingestion-only credentials and bounded buffering are useful; complete authentication-event coverage under F24 and recognize pod metadata visibility under F26. |
| OpenObserve | Local storage and email provisioning are implemented; F06 and F15 prevent the advertised missing-telemetry and incident-lifecycle guarantees. |
| Zabbix server and web | Managed templates, dashboards, and mail configuration are substantial; protect bootstrap under F04, authenticate telemetry under F22, and reject weak administrator passwords under F23. |
| Zabbix Agent | Host collectors and constrained SMART command execution are appropriate in principle; F01 currently breaks ZFS collection, and certificate monitoring should be independent of logging enablement. |
| Stalwart | Local delivery, JMAP, and authenticated external relay fit the plan; address F14, F23, and F25 while preserving the implemented removal of temporary recovery access. |
| Notification path | Direct internal SMTP followed by mailbox readback is stronger than checking SMTP acceptance alone; it remains dependent on the same host, cluster, database, and mail service that it monitors. |

### Application identity and account lifecycle

Configured callback URLs and issuer discovery are necessary but do not prove successful login, token exchange, user provisioning, or account matching. The handoff itself distinguishes callback checks from completed browser login. Each connected application should be checked with at least one intended administrator and one ordinary enabled user.

Disabling an OpenCloud identity does not necessarily revoke every existing downstream application session immediately. Native mailbox authentication in Stalwart is deliberately independent of OpenCloud. [OPERATIONS.md](OPERATIONS.md) already contains application-specific suspension and deletion guidance; its actual results should be verified on the pinned versions.

Changing a mailbox username or forwarding-domain identity can also affect the bootstrap identity used by OpenObserve. Existing root credentials stored in its metadata are not automatically renamed by changing environment variables. Keep that identity immutable after bootstrap unless an explicit supported account-change operation is added, and make the configuration validator enforce the chosen rule.

## Ansible and script review

| Area | Assessment |
| --- | --- |
| `install.py` | Root and TTY requirements, installer locking, transient runtime files, Vault handling, and a fixed entrypoint are sound choices; F03 and F08 expose lifecycle gaps, and the actual `validate` mode should be reflected consistently in documentation. |
| `install_helpers.py` | Strict structure, disk selection, dependency checks, and bounded values provide useful rejection; F07, F10, and F23 concern unapplied values, stage combinations, and password validation. |
| `preflight` | Disk safety, schema checks, dependencies, resource checks, and runtime prerequisites are valuable; pool membership is affected by F02 and memory-request budgeting does not guarantee peak workload fit. |
| `site.yml` | Fixed ordering is readable and most dependency sequencing matches the catalog; skipped stages require the explicit lifecycle policy described in F09. |
| Shared manifest rendering | Keeping resources in Jinja service templates and Secrets in private role templates follows repository rules; object application does not inherently prune resources removed from conditional rendering. |
| Shared dataset tasks | Dedicated datasets, fixed PV sizes, mountpoint checks, quotas, and ownership initialization are consistent with the architecture; ZFS quotas remain the actual capacity boundary. |
| ZFS role and storage helpers | Destructive creation is limited to the intended lifecycle and guarded by disk checks; align pool identity checks and persisted recovery state before relying on reapply. |
| k0s role | Binary pinning, encrypted mount dependencies, container-log bounds, and readiness checks are useful; apply effective network settings and document the host-wide AppArmor adjustment. |
| Networking role | Host firewall, edge resources, provider Secrets, and VPN module support are implemented; F03, F10, F13, F17, and F18 concern lifecycle, permissions, DNS convergence, and translated endpoints. |
| Intel GPU role | Firmware, driver, group, and plugin checks address hardware prerequisites; a CPU VM run cannot validate the target device behavior. |
| Database-consuming roles | Grist, Immich, Stalwart, and Zabbix include existing-role reconciliation paths; AFFiNE should use the same complete lifecycle rather than only initial creation. |
| Stalwart configuration plan | The plan and readiness helper target the current 0.16 configuration model; verify resulting directory permissions, DNS changes, queue protection, and relay behavior against the patched pinned release. |
| OpenCloud role | Identity material and persistent application configuration are separated appropriately; restoration must preserve their mutual consistency. |
| Media provisioning helpers | API configuration and credential setup are more meaningful than pod health alone; updates must preserve singleton writer semantics and completed provider/download/import behavior. |
| Logging scripts | Heartbeat generation and managed OpenObserve provisioning are simple and reviewable; the generated absence query is incompatible with notification scheduling under F06. |
| Zabbix collectors | Read-only metric collection and error logging are appropriate; catalog compatibility, unavailable telemetry, and exact privileged command forms remain important acceptance boundaries. |
| Global validators | Functional checks provide useful evidence; F10, F16, and F27 identify assumptions about edge resources, policy protection, and callback acceptance that exceed the checks. |
| Observability validators | Mailbox readback proves more than relay acceptance; a positive alert exercise does not prove heartbeat absence, recoveries, or hourly reminders. |

### Script-specific improvement priorities

The most important script changes are contract corrections rather than stylistic rewrites: normalize storage identities, accept the complete monitored dataset inventory, reconcile every advertised secret rotation, and compare owned DNS fields. Preserve the existing lean scripts and separate helpers.

Validation scripts should report exactly what they established. A successful discovery request means discovery works; a healthy HTTP endpoint means that endpoint responded; a policy name means an object with that name exists. None of those should be promoted into stronger claims about login completion, durable application state, traffic isolation, or notification delivery.

The integrity checker should receive enabled-stage context instead of assuming that every edge object exists. Existing validators should also distinguish expected absence for disabled stages from a missing resource required by an enabled stage.

### Additional maintenance details from the exported conversation

The following observations improve the lifecycle contract without establishing another present exploit or universal installation blocker.

| Area | Supported observation | Improvement |
| --- | --- | --- |
| Dataset permissions | [Shared ownership tasks](../ansible/tasks/service_dataset_permissions.yml) recursively traverse every service dataset on reapply. | Set root ownership routinely and reserve recursive ownership repair for an explicit required operation. |
| Large media libraries | The shared ownership path can traverse a large library during unrelated reapplications or rotations. | Measure traversal cost and avoid unconditional walks of established content. |
| Kernel updates | [Networking tasks](../ansible/roles/networking/tasks/main.yml) accept any `installed` DKMS status without matching the running kernel. | Require an installed module for the actual target kernel and verify module loading after reboot. |
| Kernel API transitions | [The compatibility patch](../ansible/roles/networking/files/patch_amneziawg_compat.py) rewrites shared DKMS source against the current kernel headers during the role. | Define an upgrade procedure that validates compatibility for the next kernel before relying on unattended rebuilds. |
| AFFiNE preparation | [AFFiNE tasks](../ansible/roles/affine/tasks/main.yml) remove terminally failed preparation Jobs but retain successful ones. | Define version-sensitive preparation and avoid applying changed immutable Job templates over an old successful Job. |
| Database isolation | Separate PostgreSQL roles do not alone express an explicit database-level `PUBLIC CONNECT` policy. | Review cross-database connection privileges without equating connection access with access to another application's tables. |
| Provider credentials | Separate Cloudflare secret fields do not prove distinct credentials or correctly scoped provider grants. | Verify effective permissions and consider a dedicated delegated challenge zone where practical. |
| VPN policy layers | AmneziaWG's outer egress permits broad non-cluster destinations while finer peer restrictions run inside its privileged pod. | Preserve peer ACLs and evaluate an outer destination backstop for compromise of that pod. |
| VPN DNS | A peer allowed to reach a LAN service on TCP 443 is not thereby allowed to use the LAN DNS server. | Verify explicit UDP and TCP 53 allowances for peers requiring split DNS. |
| Public administration | Several native administration interfaces are intentionally public under PLAN.md. | Decide explicitly whether MFA or restricted administration paths should strengthen the intended password-based access. |

These recommendations need application-aware implementation. Recursive ownership removal must preserve permissions needed by existing workloads. A preparation Job revision must not blindly rerun destructive operations. The kernel observations do not establish that every ordinary kernel update fails; they identify assumptions that are insufficient for a dependable update contract.

The mail design also needs a deliberate filtering boundary. A public SMTP listener accepting a local domain can receive mail addressed directly to that domain regardless of its published MX priority. If the external inbox is intended to be a mandatory filtering gateway, acceptance must prove that direct delivery cannot bypass that requirement. Otherwise, document direct local delivery as supported and verify forwarded mail with the actual provider's SPF, DKIM, and DMARC behavior. The export's speculation about automatic DMARC rejection was not verified and is not a numbered defect.

The public-DNS checker deliberately requires reverse DNS for the mail hostname. Setup documents this prerequisite, so it is not an undisclosed bug. Decide whether that prerequisite remains necessary for a deployment whose outbound delivery always uses an authenticated relay; retain the current requirement until the intended mail contract is explicitly changed.

## Security boundaries and broader improvements

### Backup and recovery are still operator responsibilities

[OPERATIONS.md](OPERATIONS.md) explicitly states that backup automation is not configured. The `backup` hierarchy identifies intended backup scope; it does not create an independent copy. RAIDZ1 tolerates one disk failure, but does not protect against accidental deletion, application corruption, stolen hardware, or complete pool loss.

Before storing important data, establish off-host encrypted backups and prove restoration. Shared PostgreSQL and application files need a consistent recovery point. OpenCloud identity material, private configuration/Vault state, encryption keys, and mail metadata need explicit inclusion. Application datasets should not be assumed mutually consistent merely because they were copied independently.

This is an acknowledged deferred capability, not a claim that the source secretly promises a completed backup implementation. It remains a major readiness dependency.

### Encryption protects a specific threat model

The ZFS key is installed on the host for automatic unlock. Encryption meaningfully protects detached data disks, but possession of the whole host and its readable boot storage can include the key. If whole-machine theft is in scope, choose a separate unlock/key-delivery model and accept its reboot-operability consequences.

The host administrator, kernel, container runtime, privileged infrastructure components, and encryption-key access are trusted boundaries. Namespace policies and user namespaces do not turn this single machine into independent physical security domains.

### Network isolation has limits beyond namespace policy

The host firewall template accepts traffic sourced from the configured pod CIDR, and its forwarding restrictions focus on the default IPv4 interface. This deserves explicit host-threat-model documentation. NetworkPolicy alone does not generally prevent pod-to-node communication, and a multi-interface deployment should not inherit an assumption that the default interface is its only ingress path.

Restrict trusted pod-source traffic to appropriate interfaces and required host ports where practical. Validate all untrusted interfaces or explicitly reject an unsupported multi-interface topology. Include Kubernetes API access in the review; an open socket and API authorization are separate protections.

Application public-HTTPS exceptions are broad destination allowances. They enable needed metadata, models, identity, and external integrations, but also permit data exfiltration by a compromised allowed application. Narrow destinations where a stable enforceable boundary exists, especially for office integration, while avoiding fragile IP allowlists for providers with changing addresses.

ARR peer rules can be narrowed from broad groups of application ports to the actual directed dependency matrix. API credentials remain important even when namespace routing is private.

### Pod and host hardening should be enforced as a contract

Many templates already disable privilege escalation, drop capabilities, use runtime-default seccomp, and avoid unnecessary service-account tokens. Some infrastructure or upstream application containers intentionally require broader capabilities or writable roots. Assess each exception against the actual runtime contract rather than applying a uniform setting that breaks the supported application.

Managed namespaces do not currently establish a Pod Security Admission enforcement baseline. Add a suitable baseline with documented exceptions, or another admission control, to keep later templates from silently broadening privileges. GPU, VPN, and host-log components will need deliberate treatment.

The k0s role sets `kernel.apparmor_restrict_unprivileged_unconfined=0` host-wide to address the signal-denial failures recorded in the live handoff. That solves a documented runtime problem but reduces a host hardening restriction for other processes too. Investigate a narrower supported profile/runtime solution when practical, and retain the current behavior until a replacement has passed the same workload and VPN recovery checks.

### Capacity needs workload evidence

Preflight budgets reserved memory requests while maximum container limits remain burstable. That is a legitimate scheduling model, but simultaneous allowed peaks can exceed real RAM. The shared PostgreSQL service, model downloads, document conversion, search indexing, and Immich imports can peak together. The live handoff already contains several OOM and ephemeral-storage incidents.

Measure these operations together on the intended hardware. Keep operating-system and ZFS ARC headroom, and size database requests with actual baseline use in mind. `shared_buffers` alone can exceed a small nominal PostgreSQL request when its configured limit is larger.

Per-dataset quotas do not reserve enough aggregate pool space for every dataset to reach its limit. Image and ephemeral-data quotas must cover the selected image set, model caches, container logs, temporary conversions, and updates. A dedicated `10Ti` PV is the intended Kubernetes declaration; it does not allocate 10TiB on the pool or override a smaller ZFS quota.

### Ephemeral caches require defined recovery

Redis and Valkey are intentionally nonpersistent. Document whether lost state consists only of reconstructible cache entries or also background jobs requiring reconciliation. Bound application concurrency and transient allocations below container limits. An eviction setting that removes required job data would not be a safe substitute for adequate memory.

### Monitoring needs an independent failure path

Metrics, logs, queries, mail delivery, and their storage share one host. A host outage, Internet outage, exhausted shared database, or broken mail service can prevent notification. The operations documentation acknowledges independent outage monitoring as external work.

Use an independent observer for host reachability and a synthetic end-to-end notification or service check. Avoid adding recursive alerts that depend on the same failing logging and SMTP path. Record the independent check's cadence and the operator's expected response.

### Reproducibility and patch management are uneven

Several images are digest-pinned, while others use version tags alone. A version tag is helpful, but a digest gives an exact reviewed artifact. Apply a consistent tag-plus-digest policy to infrastructure and public applications, with a deliberate upstream patch-review process.

The k0s release and checksum checked during upstream research exist and match; the version number is not itself a finding. User-namespace prerequisites also agree with the repository's deliberately stricter supported ZFS baseline. A matching release does not remove the need to review advisories for the complete dependency set.

## PLAN.md and documentation consistency

| Area | Current inconsistency or limitation | Required reconciliation |
| --- | --- | --- |
| Supported rotations | The installer exposes rotations that do not complete their consumer lifecycle. | Implement F03 or stop advertising those operations. |
| Cluster network inputs | Validated public values do not establish the effective k0s network. | Apply and verify F07. |
| Stage enablement | A false stage value means skip, although it can be read as stopped. | Define and enforce F09 semantics. |
| Namespace isolation | Default-deny is owned by an optional stage. | Make accepted stage combinations match F10. |
| Logout | Grist's signed-out destination is authenticated again. | Correct F11 and verify the browser flow. |
| Heartbeat alert | Documentation directs the operator to a missing-heartbeat alert whose empty result cannot notify. | Correct F06 and record live absence evidence. |
| Incident lifecycle | System-wide recovery and reminders exceed the implemented OpenObserve event-rule behavior. | Choose and document the F15 contract. |
| Network integrity | Policy-name checks are weaker than verification of required policy contents and presence. | Strengthen F16 and accurately describe existing evidence. |
| Alert SMTP routing | Parts of NETWORKING.md still describe external-relay destination allowances, while the current path is direct to Stalwart TCP 2525. | Update the narrative and connectivity matrix. |
| GPU consumers | The Intel GPU README describes a future second consumer, although Jellyfin already uses it conditionally. | Describe Immich and Jellyfin allocations and CPU fallback. |
| Media hardware | PLAN.md's hardware-oriented target and the implemented CPU fallback need one clear supported-mode description. | Explicitly document both acceptance paths. |
| Installer modes | Root instructions list four lifecycle modes, while the installer also implements `validate`. | Align entrypoint documentation. |
| Live handoff | The headline snapshot precedes later ledger updates and several references describe historical layouts. | Preserve historical evidence and add a clear final status for the current source. |
| Backup scope | Dataset names can suggest protection that remains operator-managed. | Keep the explicit backup limitation prominent in setup. |

The reviewed public schema version 11 and secrets schema version 6 agree between helpers, preflight assertions, and the public example where applicable. No schema-version mismatch was found. The per-service dataset and fixed `10Ti` PV convention is generally implemented as intended, including the declared disposable media and logging exceptions.

## Choices that should not be misreported as bugs

Jellyfin has a conditional CPU path when the Intel GPU stage is disabled. It does not always request an unavailable GPU, so a CPU-only media installation is not inherently unschedulable for that reason.

Disabling PostgreSQL `full_page_writes` on the deliberately configured direct ZFS storage is an explicit tuning choice in PLAN.md and has support in [OpenZFS PostgreSQL tuning guidance](https://openzfs.github.io/openzfs-docs/Performance%20and%20Tuning/Workload%20Tuning.html#postgresql). It should not be called an automatic corruption bug without considering the complete storage guarantees. Disabled data checksums still remove an additional corruption-detection mechanism, so recovery evidence and adherence to the intended storage path matter.

Internal alert SMTP on TCP 2525 without TLS or authentication is explicitly designed for restricted local delivery. The source does not justify calling it an open relay merely because anonymous local-domain delivery is allowed. Both network restrictions and rejected anonymous external-recipient delivery need live confirmation.

OnlyOffice's default private-address filtering initially looked like a possible split-DNS incompatibility. The pinned [WOPI client](https://raw.githubusercontent.com/ONLYOFFICE/server/v9.4.0.1/DocService/sources/wopiClient.js) and [HTTP utility implementation](https://raw.githubusercontent.com/ONLYOFFICE/server/v9.4.0.1/Common/sources/utils.js) show a distinct trusted/direct-request path after host filtering. The source does not establish the suspected blanket private-address failure, so this is not reported as an additional blocker. Actual open/edit/save acceptance remains required, and F05 concerns the missing restriction on trusted hosts.

The media namespace's default-deny and explicit gateway policies provide meaningful protection during startup. A route-helper startup race is an availability and acceptance concern; this audit does not establish an unrestricted clear-text traffic leak solely because the helper is a regular container.

## Exported-conversation reconciliation

The conversation contains useful observations, repeated findings, tentative hypotheses, and several assertions contradicted by the present implementation. Its recording is evidence of what was considered, not evidence that every suspected consequence occurs. Existing findings retain their identifiers; repeated concerns are not counted again.

| Exported topic | Result against the current source |
| --- | --- |
| Installation recovery, pool devices, monitored dataset inventory, network inputs, rotations, bootstrap, WOPI, and heartbeat behavior | Already covered by F01–F08 and strengthened where relevant. |
| Stage disablement, logout, singleton rollouts, edge privileges, alert state, policy verification, and DDNS drift | Already covered by F09–F17. |
| Translated ingress egress, AFFiNE origin, Grist identity/API behavior, Zabbix transport, weak passwords, journal filtering, proxy attribution, secret fingerprints, and callback verification | Added as F18–F27 with individual evidence and acceptance criteria. |
| Permanent Stalwart recovery administrator | Rejected because [Stalwart tasks](../ansible/roles/stalwart/tasks/main.yml) remove the temporary Secret in an `always` block and restart without recovery access on success or failure. |
| Alloy ingestion password never populated | Rejected because [logging tasks](../ansible/roles/logging/tasks/main.yml) retrieve the ingestion passcode, populate its Secret, and restart Alloy after changes. |
| Intel GPU plugin uses the wrong host kubelet path | Rejected because [GPU role defaults](../ansible/roles/intel_gpu/defaults/main.yml) set its host path to `/tank/secure/k0s/kubelet/device-plugins`. |
| k0s telemetry is automatically enabled | Rejected because [the pinned telemetry implementation](https://raw.githubusercontent.com/k0sproject/k0s/v1.36.2%2Bk0s.0/pkg/apis/k0s/v1beta1/telemetry.go) defaults it to disabled. |
| OnlyOffice must fail on every private split-DNS callback | Rejected because the pinned WOPI request implementation has the distinct path discussed above. |
| Every AmneziaWG peer can reach every host or LAN port | Rejected because in-pod peer ACLs restrict destinations beyond the broader outer policy. |
| Passive Zabbix agent is exposed throughout the LAN | Rejected because the agent binds to loopback; F22 concerns the reachable server receiver. |
| OpenObserve ingestion passcode is necessarily an unrestricted administrator password | Not supported by the provisioning flow or the reviewed ingestion-token behavior. |
| AFFiNE's manual OIDC client-secret entry is missing automation promised by the repository | Rejected because setup explicitly requires the manual application step. |
| PostgreSQL ZFS tuning, CPU-only Jellyfin, or anonymous restricted internal SMTP inherently violate the plan | Rejected for the reasons in the preceding section. |
| Version differences alone prove Zabbix agent/server incompatibility | Not established because compatibility must be checked against the supported protocols and exercised features. |
| Public salt fixes exposed secret checksums | Rejected because a public salt still permits offline candidate verification. |
| All mail forwarding necessarily fails DMARC or omits required DKIM signing | Unverified because the actual forwarder and authenticated relay affect the authentication path. |
| Broad outer VPN egress proves a startup traffic leak | Not established because the separate pod policy and peer-routing protections must be considered together. |

The export also raised certificate lifetime changes. This is future maintenance work rather than a demonstrated current renewal failure. [Let's Encrypt's published schedule](https://letsencrypt.org/2025/12/02/from-90-to-45) moves the default profile to 64 days on 10 February 2027 and 45 days on 16 February 2028, with an optional shorter profile available earlier. Review Traefik and Stalwart renewal settings together with the fixed expiry-warning thresholds before adopting shorter profiles. Do not assume that a threshold appropriate for the present lifetime remains appropriate for every future profile.

Recovery cleanup that normally executes still cannot guarantee cleanup after sudden host power loss. A bounded interrupted-bootstrap exercise remains useful, but this conditional operational concern does not justify describing Stalwart's recovery credentials as permanently deployed.

## Recommended implementation order

1. Fix the collector inventory and pool identity checks.
2. Implement a safe early-create resume boundary.
3. Apply accepted cluster network configuration and verify translated pod-to-edge connectivity.
4. Protect administrator bootstrap before publishing public routes.
5. Restrict WOPI integrators and narrow edge Secret authorization.
6. Complete every advertised credential rotation.
7. Correct heartbeat absence notification and define log incident semantics.
8. Reconcile stage disablement, singleton rollouts, AFFiNE origin, and Grist identity/API behavior.
9. Adopt the reviewed Stalwart patch and correct DDNS field reconciliation.
10. Authenticate monitoring transport and complete password, proxy, log, and validation controls.
11. Establish independent backups, restoration evidence, and external outage monitoring.
12. Complete hardware and peak-capacity acceptance on the target host.

## Live acceptance still needed

All installation and reapplication work should use `sudo python3 ansible/install.py`. The installer manages runtime configuration and Vault credentials; bypassing it with a direct playbook invocation would not verify the supported entrypoint.

| Acceptance area | Required evidence |
| --- | --- |
| Fresh create | Every enabled stage completes from the intended clean host using only the selected data disks. |
| Interrupted create | Each documented recovery boundary resumes without repeating disk erasure. |
| Reapply | A complete reapply preserves data and does not reject the pool or leave duplicate writers. |
| Reboot | Encryption unlock, mount ordering, cluster startup, services, and retained data recover after complete deployment. |
| Custom network | A non-default supported configuration matches the effective cluster and all firewall/VPN consumers. |
| Stage disablement | A disabled installed application is stopped and unpublished according to the documented lifecycle. |
| Credential rotation | Every advertised rotation updates its authoritative service and running consumers. |
| Administrator bootstrap | No public client can claim the initial administrator or use vendor defaults during setup. |
| Browser identity | Completed logins, ordinary-user authorization, logout, and disabled-user behavior work in each connected application. |
| Pod identity routing | Issuer HTTPS requests succeed from each consuming pod through the actual hostPort and policy path. |
| AFFiNE origin | Fresh configuration uses the public HTTPS origin for links, OAuth, and browser mutations. |
| Grist identity changes | Proxy reauthentication and retained application state cannot disagree about the current user. |
| Grist API | Native credentials work through the supported route without allowing identity-header forgery. |
| Office integration | Real document editing persists changes and unrelated WOPI hosts are rejected. |
| Search and extraction | Representative documents are extracted and indexed through the actual applications. |
| Immich | Upload/readback and real machine-learning inference work in the supported CPU and GPU modes. |
| Media | Indexer discovery, download, import, library playback, and intended transcoding work end to end. |
| VPN isolation | Cold start, tunnel loss, gateway restart, server outage, and recovery retain denied direct egress. |
| Mail | Native login, inbound forwarding, local delivery, authenticated outbound relay, and rejection of unauthorized external relay work. |
| Monitoring | ZFS/ECC/SMART telemetry and stale-collector handling are correct for the actual hardware. |
| Monitoring authenticity | A LAN client lacking the agent credential cannot submit accepted data for the monitored host. |
| Host security logs | Controlled local privilege and firewall events reach the central log stream. |
| Proxy attribution | Remote/local classification and client-IP audit survive forwarding without trusting arbitrary headers. |
| Notifications | Positive alerts, heartbeat absence, recovery, and hourly reminders reach the configured mailbox. |
| Policy integrity | Missing or modified mandatory policies fail verification and actual prohibited traffic is denied. |
| Kernel upgrade | The selected next kernel builds and loads the VPN module and preserves connectivity after reboot. |
| Capacity | Concurrent indexing, inference, conversion, imports, and mail fit RAM and quota headroom. |
| Restoration | Independent backups restore a consistent application and identity state to a recoverable host. |

## Markdown review inventory

| Group | Files read |
| --- | --- |
| Repository | `AGENTS.md`, `PLAN.md`, `README.md`, `TODO.md`. |
| Operations documentation | `docs/LIVE_TEST_HANDOFF.md`, `docs/NETWORKING.md`, `docs/OPERATIONS.md`, `docs/SETUP.md`, `docs/VALIDATION.md`. |
| Kubernetes guidance | `k0s-services/AGENTS.md`, `k0s-services/README.md`. |
| Application READMEs | `affine`, `grist`, `immich`, `jellyfin`, `onlyoffice`, `opencloud`, `stalwart`. |
| Infrastructure READMEs | `alloy`, `arr`, `bleve`, `intel-gpu`, `manticore`, `meilisearch`, `networking`, `openobserve`, `postgres`, `redis-affine`, `tika`, `zabbix`. |
| Zabbix documentation | `zabbix/ZABBIX.md`. |

The README names in the application and infrastructure rows refer to `k0s-services/<name>/README.md`. This report is a new thirty-second Markdown file and is not part of its own input inventory.
