# Live installation work summary and remaining goals

## Goals and requirements

The goal is to make the repository's installation scripts produce a working private cloud from a clean machine, then demonstrate that every enabled service works. The live VM run must expose actual installation failures, correct their causes in repository source, and continue until the complete installation and validation path succeeds.

Success requires more than creating Kubernetes resources or observing Running pods. Each service needs an explicit acceptance condition, such as an authenticated database query, a file upload and readback, or delivery of an alert to the configured mailbox. The final result must also survive reapplication and a guest reboot.

| Requirement | Acceptance condition |
| --- | --- |
| Supported installation path | Creation, reapplication, and validation run through `ansible/install.py`. |
| Complete installation | Every enabled stage finishes and its functional checks pass. |
| Storage safety | Only the selected two 40GiB data disks form the pool. |   
| Constrained resources | Services boot and perform their checked operations within the 20GiB guest budget. |
| Persistent state | Encrypted datasets unlock and services recover after reboot. |
| Separate verification | Reusable checks live in validation folders and run after installation. |
| Configuration-driven checks | Domains, recipients, endpoints, credentials, and expected settings come from configuration. |
| External dependencies | Local fixtures exercise integrations wherever practical. |
| Manual prerequisites | Unautomatable provider and hardware steps are documented in SETUP.md. |
| Reproducible fixes | Required behavior is implemented in source templates and scripts. |
| Evidence | Each result distinguishes implemented checks, successful live execution, and remaining gaps. |

The repository's layout and configuration contracts remain requirements. Persistent services retain separate quota-controlled datasets and dedicated 10Ti PV/PVC capacities. Plaintext secrets stay outside the repository, and checks must preserve existing application data. PLAN.md specifies the target state; planned behavior counts as complete only after implementation and appropriate live evidence.

## Snapshot status

Snapshot: 2026-10-05 at approximately 12:38 UTC.

**The whole-system installation is incomplete.** The 12:22:37 UTC reapply stopped at 12:29:25 UTC when AFFiNE reused its already failed database-preparation Job. All preceding enabled stages passed this reapply; Immich and observability have not yet been installed. No installer is running at this snapshot.

## Current execution state

This section and the progress ledger are updated as work proceeds; the evidence tables below retain results from earlier steps until explicitly superseded.

- Root coordinates installation runs and records progress in this file.
- The observability agent investigates AFFiNE Job lifecycle and migration locking.
- The networking agent diagnoses stalled VPN recovery after a passing isolation check.
- The application agent reviews Immich inference and tests available application integrations.
- The next installer run waits for the AFFiNE retry correction and completion of network outages.

## Progress ledger

| Time (UTC, 2026-10-05) | Step | Result and next action |
| --- | --- | --- |
| 12:35 | Resumed work and inspected live processes, Pods, and installer logs. | No active installer; earlier stages remain Ready, and the last reapply failed on an existing terminal AFFiNE Job. |
| 12:35 | Resumed the three service agents. | Investigate safe Job recreation and migration locking, finish VPN outage acceptance, and review application integration checks. |
| 12:35 | Checked memory, dataset usage, and live workload metrics. | About 14GiB RAM and 25.3GiB logical pool capacity remain available; existing workloads fit their trial caps. |
| 12:35 | Authorized the isolated VPN outage fixture. | New installer runs are held until the gateway and mock server are restored. |
| 12:35 | Ran the identity validator against configured OpenCloud HTTPS routing. | Issuer discovery and all twelve configured callback requests passed; this does not prove completed login or token exchange. |
| 12:36 | Corrected AFFiNE retry lifecycle in repository source. | Reapply now removes only an unsuccessful terminal preparation Job before retrying; successful Jobs are preserved, and live execution is pending. |
| 12:37 | Ran the expanded media VPN fixture. | Tunnel-down isolation passed, but recovery exceeded its bound before the server-outage phase; temporary policy and host rules were cleaned up. |
| 12:37 | Inspected gateway restart logs. | Gluetun stalled at VPN stopping; investigate signaling its privilege-dropped OpenVPN child before changing timeout bounds. |
| 12:37 | Confirmed gateway signal permission failure with `kill -0`. | Root cannot signal the privilege-dropped OpenVPN child; the capability mask lacks KILL, providing evidence for a narrow capability correction. |
| 12:38 | Added KILL to the gateway's existing minimal capabilities in source. | A media validator asserts the capability; apply the matching live change and repeat bounded outage recovery next. |
| 12:39 | Checked the Immich ML probe against pinned v3.1.0 source. | Multipart request and response contracts match; default buffalo_l model download and the 1GiB CPU inference cap still need live execution. |
| 12:39 | Rolled out the gateway KILL capability correction. | Gateway is Ready and authenticated; the previously denied signal-permission check now passes, and full outage acceptance is rerunning. |
| 13:22 | Captured AFFiNE lock holders during a retried preparation Job. | Prisma failed to stop its first schema engine with `kill EACCES`; that orphan held lock `72707369` while the second engine waited. |
| 13:23 | Inspected kernel audit records. | AppArmor denied signals from `cri-containerd.apparmor.d` to the stacked `cri-containerd.apparmor.d//&unconfined` label; gluetun and OpenCloud hit the same denial. |
| 13:24 | Set `kernel.apparmor_restrict_unprivileged_unconfined=0` live and in the k0s role. | Prisma migrations passed and denials stopped after restarting affected pods; k0s validation asserts the setting. |
| 13:25 | Reran AFFiNE preparation with a non-restarting debug Job. | Data migration failed because Manticore was OOM-killed at 256MiB while AFFiNE created indexer tables; the trial cap is now 512MiB. |
| 13:31 | Started a reapply through the installer driver. | AFFiNE preparation, application, and site validation passed; Immich server and ML crash-looped. |
| 13:45 | Inspected Immich failures. | Service links injected `IMMICH_PORT=tcp://...`; all Immich pods now set `enableServiceLinks: false`. |
| 14:05 | Reran to Immich. | The server was OOM-killed at 1GiB during geodata import, and the replacement ML pod could not schedule beside the old crash-looping pod. |
| 14:06 | Corrected Immich sizing and rollout. | Server cap is 2GiB, ML uses Recreate with a 1GiB ephemeral request, and the trial ephemeral quota is 12G. |
| 14:06 | Pre-reviewed observability and Zabbix. | The SMTP resolver rejected the LAN relay; it now also accepts configured `local_network_cidrs`. OpenObserve and Alloy trial caps are 1536MiB and 512MiB. |
| 14:07 | Started the next reapply. | Preflight rejected the summed memory limits; trial caps were rebalanced within the per-service minimums. |
| 14:35 | Reran with PostgreSQL at 512MiB. | PostgreSQL was OOM-killed when Immich connected; PostgreSQL returned to 1GiB and Stalwart moved to 256MiB. |
| 14:50 | Reran to Immich. | Applying the ML Recreate strategy failed against the live RollingUpdate object; the old Deployment was deleted once for this trial. |
| 15:06 | Reran to Immich. | Server and ML reached Ready and passed ping checks; CPU inference returned HTTP 500 because Hugging Face downloads wrote to an unwritable home cache. |
| 15:12 | Set `HF_HOME` and `MPLCONFIGDIR` under the ML cache volume and restarted the reapply. | Pending. |

This document records the live test and its handoff state. [PLAN.md](../PLAN.md) remains the target specification, and [TODO.md](../TODO.md) tracks broader outstanding repository work. Some unchecked TODO items now have partial or completed evidence from this run; they still require reconciliation with the final acceptance results.

## Requested outcome

- Install every enabled stage through `ansible/install.py`.
- Fix installation failures and continue through the complete path.
- Separate installation code from reusable service validation.
- Validate actual service behavior using global configuration.
- Mock external dependencies during the VM trial.
- Document real external prerequisites in [SETUP.md](SETUP.md).
- Fit the installation into the available RAM and data disks.
- Delegate service investigations to Luna agents using xhigh reasoning.

## Test environment

| Item | Trial configuration |
| --- | --- |
| Hypervisor | VMware Workstation / Player |
| Guest | Ubuntu 26.04.1, Linux 7.0.0-38 |
| CPU | Eight guest vCPUs on an Intel Core i7-12700K host |
| Memory | 20GiB |
| Operating-system disk | Separate `/dev/sda` disk |
| Data disks | Two 40GiB disks selected through persistent PCI/SCSI paths |
| Storage | Encrypted `tank/secure` on a two-disk RAIDZ1 pool |
| Usable pool capacity | Approximately 38.5GiB before service data |
| ZFS ARC | 1GiB cap |
| Cluster | k0s v1.36.2+k0s.0 |
| Host address | `192.168.75.131` |
| Trial domain | `private-cloud.test` |
| Acceleration | CPU workloads; Intel GPU stage disabled |

The guest rebooted during the test. The pool, encryption unlock, native mounts, k0s, and existing service data survived that reboot. A second reboot after the complete installation remains necessary.

## Work completed

### Installer, configuration, and storage

- Read the repository Markdown documentation, including PLAN.md and repository instructions.
- Installed the host packages and Ansible collections needed for the live run.
- Added disk-path fallback for VMware disks without serial-based identifiers.
- Corrected ZFS pool-property arguments and native encryption-unit handling.
- Corrected encrypted mount dependency checks and mount-cache refresh behavior.
- Corrected RAM-unit parsing and coordinated configuration schema changes.
- Sized dataset quotas and memory limits for the constrained guest.
- Preserved dedicated 10Ti PV/PVC capacities while enforcing actual dataset quotas.
- Corrected k0s first-install discovery and worker-profile startup races.
- Increased the trial ephemeral-storage quota to 8G after scheduling failures.
- Added private live installer logs and clearer failure-task reporting.

### Validation layout

Service roles now keep their checks in `ansible/roles/<stage>/validation/`. Shared Python validators and integration fixtures live under `ansible/validation/`, including separate `media/`, `observability/`, and `mocks/` directories. Observability alert validation was moved out of the installation script folders.

Roles invoke their validators after setup. The installer also runs the installed-system validation after all enabled stages complete, and its `validate` action reuses those checks. The complete automatic validation sequence has not yet run successfully because installation has not reached its end.

Validators use configured hostnames, ports, credentials, and service properties. Added checks include database queries, API authentication, text extraction, cache round trips, OpenCloud file operations, ARR configuration, inbound mail restrictions, and service namespace isolation. A CPU Immich inference check has been added but has not yet run against a deployed service.

## How verification works

### Execution and failure handling

Verification has two entry paths. During installation, each role checks its service after configuring it. After all stages finish, the installer invokes `ansible/validate.yml` for the whole system. Selecting `validate` in the installer runs the installed-system checks independently without replaying installation roles.

The validation playbook generates transient cluster credentials, checks storage and cluster state, invokes the enabled roles' validation files, and then checks shared identity, network, and observability integrations. Disabled stages are skipped using `private_cloud.stages`. Assertions and nonzero command results stop the flow; a service failure must be diagnosed and corrected before acceptance can proceed.

Ansible owns orchestration, readiness waits, and assertions. Python helpers perform operations that need protocol handling or response inspection. For example, role tasks pass JSON input to `check_application.py`, which can reach a configured Kubernetes Service and check the expected HTTP status or JSON response. Shared HTTP, application, and mail helpers keep that plumbing separate from service-specific acceptance logic.

Checks use bounded waits for startup and dependency availability. A timeout means acceptance failed or remains unresolved; it does not count as a successful installation. Preparation Jobs must finish successfully, and terminal failures should be reported without waiting through the full startup timeout.

### What the checks establish

| Layer | Checks | Purpose |
| --- | --- | --- |
| Storage | Pool health, encryption state, dataset quotas, mounts, and native unit dependencies. | Confirm persistent data is available and has the intended startup ordering. |
| Cluster | Controller and node readiness, storage paths, volumes, and workload rollouts. | Confirm workloads can be scheduled and access their storage. |
| Service protocols | SQL queries, authenticated APIs, Tika extraction, and Redis/Valkey round trips. | Confirm the service can perform a useful operation. |
| Application storage | OpenCloud WebDAV upload, exact-content readback, and deletion. | Confirm authentication and writable storage work together. |
| Routing and identity | Configured HTTPS routes, certificate trust, issuer discovery, and client callbacks. | Confirm services are reachable through the intended integration paths. |
| Isolation | User namespace checks, VPN binding, allowed HTTPS traffic, and blocked SSH traffic. | Confirm selected security boundaries behave as intended. |
| Monitoring | Heartbeat ingestion, managed alert configuration, and synthetic notification delivery. | Confirm the monitoring path reaches the configured mailbox. |
| Recovery fixtures | Tunnel interruption, server outage, and subsequent recovery. | Confirm failures block traffic appropriately and recovery restores service. |

Some checks make temporary changes. Cache checks create short-lived values, file checks create disposable content, and alert checks generate synthetic events. Their cleanup is part of the verification path. Outage fixtures deliberately interrupt connectivity and require explicit restoration before other validation continues.

The local mock harness is separate from normal service verification. It supplies real local protocol endpoints for the VM trial, including TLS SMTP and OpenVPN, while mocking provider-specific behavior such as Cloudflare record storage and ACME ownership checks. Passing a fixture-backed integration proves only the behavior exercised by that fixture.

### How verification is developed

Validator development follows the service's acceptance requirements and the pinned software version. Existing verification tasks are moved into the role's validation folder so installation and independent validation use the same implementation. Missing checks are added around observable behavior rather than duplicating manifest values.

1. Identify a useful operation and its expected result for the service.
2. Check the pinned version's official documentation or source for the supported protocol.
3. Derive deployment-specific values from global configuration and role variables.
4. Put orchestration in role validation tasks and protocol helpers in separate Python files.
5. Run the check against the actual installed service.
6. Inspect logs, endpoints, resources, and dependencies when it fails.
7. Correct the source and rerun through the supported installer.
8. Record successful evidence and any untested acceptance conditions.

This process exposed failures that readiness alone missed. Grist's original probe followed an HTTPS redirect to an HTTP-only listener; the pinned `/status` route provides a direct health response. The media proxy listened while tun2socks was attached incorrectly; stronger checks now inspect the actual tunnel attachment. OpenCloud reached a usable state only after authenticated file operations exposed and guided repair of its incomplete first-boot identity state.

There is no separate unit-test or dry-run suite in this repository. The primary evidence is live execution of the installer and validators. Parsing or diff checks help catch editing mistakes but cannot demonstrate that a service works. New code remains marked unproven until it runs successfully against the deployed version.

### Verification still to develop or complete

The added Immich inference validator sends a generated image to the CPU ML service and checks the returned dimensions and detection-result consistency. Its first execution may download model weights, so both external download availability and the cache budget need live verification. A blank input can exercise inference without proving recognition accuracy on real photographs.

Browser login, document editing, public mail routing, physical GPU behavior, and representative concurrent workloads need acceptance beyond basic protocol checks. The remaining-goals section below separates those checks from the immediate installation blockers. [VALIDATION.md](VALIDATION.md) documents individual service coverage and still needs reconciliation with the final run.

## Service fixes

| Area | Main corrections |
| --- | --- |
| Traefik | Discovered API endpoint egress, Node read permissions, replacement strategy, and SMTP destination port preservation. |
| AmneziaWG | Linux 7 DKMS compatibility, forwarding sysctl allowlist, peer-secret rollout checksum, and precise HTTPS egress through Traefik. |
| Media | Correct tun2socks flags, real tunnel health checks, startup capabilities, restart-safe routing, and bounded ARR configuration retries. |
| ARR configuration | Corrected comparisons for write-only secret fields to make reapplication idempotent. |
| Jellyfin | Raised trial dataset quotas to satisfy its startup free-space requirement. |
| Stalwart | Excluded configuration Jobs from service endpoints and waited for network and PostgreSQL readiness. |
| PostgreSQL | Aligned expected extension versions with the pinned image. |
| Manticore | Used the supported raw SQL HTTP endpoint. |
| OnlyOffice | Selected a Ready pod and inspected its own process namespace during validation. |
| OpenCloud | Used the required NATS file-ID cache and propagated initialization failures. |
| Grist | Corrected administrator-email matching and used `/status` for Kubernetes health probes. |
| AFFiNE | Added terminal failure detection and safe recreation of failed preparation Jobs; migration locking remains unresolved. |

OpenCloud also needed recovery from interrupted first-boot state. ZFS snapshots and private archives preserve the affected generated metadata and incomplete identity database. Regenerating those specific artifacts restored authenticated file operations without deleting user data. These were diagnostic repairs on this trial machine; production installation does not automatically erase existing metadata or identity databases.

## Live evidence obtained

| Component | Observed result | Remaining acceptance |
| --- | --- | --- |
| ZFS and k0s | Online encrypted pool, mounted datasets, Ready node, and recovery after a guest reboot. | Recheck every final dataset and repeat reboot after all stages finish. |
| PostgreSQL | TCP `SELECT 1` and expected pgvector/VectorChord versions passed. | Confirm all downstream applications work with their databases. |
| Meilisearch | Authenticated index listing passed. | Exercise application-driven search. |
| Tika | Text extraction passed. | Exercise representative uploaded documents. |
| Manticore | Raw SQL `SELECT 1` passed. | Exercise application queries. |
| Redis for AFFiNE | SET/GET/DEL passed. | Confirm AFFiNE uses it successfully. |
| Traefik and DDNS | Installed routes responded, and the actual DDNS Job updated all ten records through the mock API. | Complete final route validation and real public-provider acceptance. |
| AmneziaWG | A fresh peer handshake and trusted Jellyfin HTTPS request passed; SSH access was blocked. | Repeat from a separate client and verify every configured access rule. |
| Media and ARR | Workloads reached Ready, API configuration passed, and repeated configuration reported no changes. | Complete outage/recovery fixtures and real download workflows. |
| Media VPN | Authenticated OpenVPN tunnel established; baseline traffic passed and taking down `tun0` blocked traffic. | Prove bounded recovery and mock-server outage behavior in one complete run. |
| Jellyfin | Service booted under the trial cap. | Record final transcoding, library, playback, and login acceptance. |
| Stalwart | Authenticated JMAP discovery, trusted certificate issuance, forwarded mail, and inbound recipient restrictions passed. | Validate managed alerts and real external mail delivery. |
| OnlyOffice | WOPI discovery and a distinct user namespace passed. | Open, edit, and save a document through OpenCloud. |
| OpenCloud | Authenticated WebDAV and LDAP checks passed; configured issuer and twelve callback requests also passed. | Browser sign-in, search indexing, token exchange, and downstream identity flows. |
| Grist | `/status` returned HTTP 200 and the corrected workload reached Ready without probe-driven restarts. | Authenticated document creation through the configured identity flow. |
| AFFiNE | Dependencies and preparation resources were created; migration Job failed. | Fix migration, boot the application, and validate its behavior. |
| Immich | CPU validation code is prepared; service is not installed. | Boot server and ML, execute inference, and upload media. |
| OpenObserve and Alloy | Validation code is prepared; services are not installed. | Prove ingestion, alerts, delivery, and recovery. |
| Zabbix server, web, and agent | Validation code is prepared; stages are not installed. | Prove monitoring, problem/recovery delivery, and agent collection. |

Ready status alone is not full functional acceptance. Earlier successful probes must be rerun against the final rendered system.

## External fixtures and their limits

| Fixture | What the trial exercises | What remains external |
| --- | --- | --- |
| HTTPS Cloudflare API | The real DDNS Job and configured record names. | Real token permissions, authoritative DNS, and public propagation. |
| Local ACME server | Account registration, CSR signing, and configured certificate hostnames. | Domain ownership, real DNS-01 challenges, JWS verification, and provider renewal. |
| TLS SMTP relay | Authenticated relay submission and forwarding into Stalwart. | External inbox rules, public mail routing, deliverability, and mail reputation. |
| OpenVPN server | A real authenticated tunnel and controlled outage fixtures. | Provider-specific configuration and external routing. |
| Local CA and DNS | Trusted trial hostnames and cluster routing. | LAN/VPN client split DNS and public certificates. |

- The trial sends OpenObserve mail in plaintext to the local relay fixture on the same port.
- Public-CA TLS from OpenObserve to the real relay remains external acceptance.
- Fixture trust injection sets `ZO_SMTP_ENCRYPTION=none` on OpenObserve, and the watcher restores it after reapply.
- The logging validation asserts `ssltls`, so it conflicts with the patched trial Deployment.

Private mock artifacts now persist in `/var/lib/private-cloud-live-test` with restricted permissions. Stale PID files are discarded after reboot. Ansible reapplication can overwrite injected mock CA mounts and Traefik certificate configuration, so local fixtures require restoration before final trial validation.

## Resource findings

| Service | Trial memory cap | Evidence |
| --- | --- | --- |
| PostgreSQL | 1GiB | Approximately 61MiB observed idle. |
| Meilisearch | 256MiB | Approximately 33MiB observed idle. |
| Tika | 512MiB | Approximately 212MiB observed idle. |
| Manticore | 256MiB | Approximately 63MiB observed idle. |
| Redis for AFFiNE | 128MiB | Approximately 17MiB observed idle. |
| OnlyOffice | 2GiB | Approximately 960MiB observed during startup. |
| OpenCloud | 1GiB | Boot and authenticated storage operations passed. |
| Grist | 512MiB | Approximately 260MiB observed after probe correction. |
| Stalwart | 512MiB | Boot and mail protocol checks passed. |
| Sonarr / Radarr | 384MiB each | Ready workloads and API configuration passed. |
| Prowlarr / qBittorrent | 256MiB / 192MiB | Ready workloads and API configuration passed. |
| Jellyfin / OpenVPN gateway | 512MiB / 128MiB | Services booted. |
| AFFiNE | 1GiB application; 2GiB preparation Job | Application startup is unproven. |
| Immich server / CPU ML | 1GiB each | Configured; startup and inference are unproven. |
| OpenObserve / Alloy | 1GiB / 256MiB | Configured; startup is unproven. |
| Zabbix server / web | 1GiB / 512MiB | Configured; startup is unproven. |

These are trial caps and observed footprints, not established minimum requirements. Production sizing and concurrent workload capacity remain untested. Physical Intel GPU access is unavailable in this guest; acceleration needs a separate hardware acceptance run.

## Goals left to fulfill

### 1. Resolve AFFiNE preparation

The previous preparation Job reported Prisma `P1002` while waiting ten seconds for PostgreSQL advisory lock `72707369`. PostgreSQL was reachable, and no AFFiNE application Deployment existed. The lock holder was not captured, so the root cause remains unknown.

- Capture granted locks, waiting sessions, and blocking PIDs during the next attempt.
- Identify why sequential preparation commands retain or contend for the migration lock.
- Implement a source correction without blindly disabling advisory locking.
- Require preparation completion and a Ready AFFiNE application.
- Run health, database, workspace, and identity acceptance.

### 2. Finish the remaining installation stages

- Install Immich and execute the added CPU model-inference validator.
- Confirm model downloads fit the actual storage and memory budget.
- Install OpenObserve and Alloy and verify timestamped ingestion.
- Install Zabbix server, web, and agent and verify their configured APIs and collectors.
- Deliver actual synthetic OpenObserve and Zabbix notifications to Stalwart.
- Correct every remaining failure through the supported installer path.

### 3. Complete network and application acceptance

- Repeat the full media VPN interruption and bounded recovery fixture.
- Stop the mock VPN server and prove traffic remains blocked until recovery.
- Recheck canonical AmneziaWG policy after final reapplication.
- Exercise OpenCloud search and OnlyOffice document editing.
- Exercise browser identity flows for OpenCloud, Grist, AFFiNE, and Immich.
- Verify Jellyfin login, Quick Connect, playback, and CPU transcoding.
- Complete applicable identity lifecycle and observability gaps in TODO.md.

### 4. Prove the complete installation flow

- Finish one complete reapply with all enabled stages passing.
- Require automatic final validation to succeed.
- Run the independent installer `validate` action successfully.
- Remove temporary diagnostic policy objects and restore interrupted fixtures.
- Reboot the completed guest and rerun validation.
- Reconcile TODO.md and acceptance documentation with recorded evidence.

The initial disk creation was exercised, but later stages required source fixes and selective diagnostic repairs. A clean rebuild using the final source is still needed to prove an uninterrupted installation from blank disks. That rebuild must preserve any required handoff artifacts first.

### 5. Complete real deployment prerequisites

- Follow the one-off provider and router steps in SETUP.md.
- Repeat certificate issuance and renewal against an owned domain.
- Verify public DNS, mail authentication records, and external forwarding.
- Verify WAN reachability and firewall restrictions from another network.
- Replace mock endpoints and credentials with real provider configuration.
- Test physical GPU acceleration on accessible hardware.
- Size quotas and RAM for actual workload growth.

## How to resume

Use the repository root and the supported interactive entrypoint:

```sh
sudo python3 ansible/install.py
```

Check whether an installer is already running before starting another. Select `reapply` to continue installation or `validate` to check an installed system. Do not invoke `ansible-playbook` directly.

For this VM, restore external fixtures when needed:

```sh
sudo python3 ansible/validation/mocks/live_test.py restore
```

Live installation output is recorded privately in `/run/private-cloud/install-live.log`; persistent trial artifacts and per-run transcripts are under `/var/lib/private-cloud-live-test`. Runtime files under `/run` disappear at reboot. Credentials must remain outside this document and outside plaintext repository files.

See [LIVE_TEST.md](LIVE_TEST.md) for the acceptance record, [VALIDATION.md](VALIDATION.md) for validator coverage, and [SETUP.md](SETUP.md) for manual prerequisites. These documents still need final updates after the remaining live checks complete.
