# Operations contract

This document defines the production conditions around the automation in this repository.

The installer creates a RAIDZ1 pool, an encrypted dataset hierarchy, quotas, local persistent volumes, a single-node k0s cluster, and the configured workloads.

The installer does not currently schedule snapshots, replicate backups, restore data, configure public DNS, terminate application TLS, change firewall or NAT rules, configure an external heartbeat, or deliver alert notifications.


## Implementation references

| Area | Current source |
| --- | --- |
| Pool creation, encryption key, datasets, and scrub | [ZFS role](../ansible/roles/zfs/tasks/main.yml) |
| k0s datasets, quotas, and controller setup | [k0s role](../ansible/roles/k0s/tasks/main.yml) |
| PostgreSQL image and ZFS properties | [PostgreSQL defaults](../ansible/roles/postgres/defaults/main.yml) |
| PostgreSQL durability and resource settings | [PostgreSQL workload](../k0s-services/postgres/templates/deployment.yaml.j2) |
| Stalwart ACME, domains, accounts, and relay plan | [Stalwart plan](../ansible/roles/stalwart/templates/plan.ndjson.j2) |
| Stalwart public NodePorts | [Stalwart service](../k0s-services/stalwart/templates/public-service.yaml.j2) |
| Draw.io extension download and remote editor | [OpenCloud workload](../k0s-services/opencloud/templates/deployment.yaml.j2) and [app configuration](../k0s-services/opencloud/templates/apps-configmap.yaml.j2) |
| Public values, secrets, and stage selection | [Example configuration](../ansible/config/private-cloud.example.yml) |
| Jinja manifest rendering | [Shared renderer](../ansible/tasks/render_manifests.yml) |
| k0s release pin | [k0s defaults](../ansible/roles/k0s/defaults/main.yml) |
| Zabbix host settings | [Service catalog](../ansible/service_catalog.yml) |

## Backup and restore

Datasets under `tank/secure/backup` are eligible for backup, but their names do not create a backup.

The operator must implement all of these controls:

- Create application-consistent recovery points at an interval within the recorded RPO.
- Replicate recovery points to the recorded independent destination.
- Retain recovery points according to the recorded schedule.
- Monitor the age and completion status of every backup class.
- Prevent the managed host from silently deleting every independent copy.
- Test restoration within the recorded RTO.
- Record the last successful restore exercise.

Snapshots on `tank` alone do not survive loss of this host or pool.

### Coordinated application recovery

PostgreSQL holds metadata for Stalwart, Grist, AFFiNE, and Zabbix while those services also use their own file datasets.

A valid recovery point must preserve database and file relationships:

- Stop writes or use application-aware backup mechanisms before the recovery boundary.
- Record the common recovery-point identifier and timestamp.
- Back up the complete PostgreSQL cluster and every related application dataset.
- Restore PostgreSQL and related files to the same coordinated point.
- Start PostgreSQL before database-backed applications.
- Rebuild disposable indexes only after their sources are authoritative.
- Reject a mixed-time restore unless an application-specific recovery procedure proves it safe.

### Recovery material

Keep encrypted, offline copies of these items outside the managed host:

- `ansible/config/private-cloud.yml`.
- `ansible/config/private-cloud.secrets.yml`.
- The Ansible Vault password.
- `/etc/zfs/keys/tank-secure.key`.
- The repository revision used for deployment.
- Host bootstrap, network, firewall, and DNS records.
- Backup credentials and restoration instructions.
- Deployment records for the host, network, and recovery process.

Store the Vault password, ZFS key, and backup credentials so one compromised copy does not expose every backup.

The installer writes `/etc/zfs/keys/tank-secure.key` as root-owned mode `0600` and configures automatic dataset unlock from it.

Anyone who can read that host file can unlock the encrypted dataset, so disk encryption does not protect data from a compromised running host or recovered boot disk containing the key.

Do not place the only recovery copy of the key or Vault password on `tank`.

### k0s control plane

Back up k0s control-plane state separately by following the upstream [k0s backup and restore procedure](https://docs.k0sproject.io/stable/backup/).

A k0s backup does not include application PV data, so it cannot replace the coordinated application-volume backup.

Copy the k0s archive to the independent destination and protect it as sensitive cluster material.

Restore it with the k0s version pinned in the deployed repository revision and the matching data-directory layout before rebinding application volumes.

## Public networking

The Kubernetes manifests expose fixed NodePorts, but the repository does not provide the public edge.

Before exposure, the operator must provide:

- Public A and AAAA records for each configured hostname.
- A reverse proxy or layer-four forwarding design.
- Certificate issuance and renewal ownership.
- Inbound firewall and NAT rules for approved services.
- WebSocket forwarding for applications that require it.
- Trusted proxy and forwarded-header settings.
- A working path from pods to every configured public hostname.

Test public hostnames from an external network and from inside the cluster.

Split-horizon DNS, hairpin NAT, or an internal proxy route may satisfy pod access, but the operator must record the selected method.

### TCP port 443

Record one owner for public TCP port 443 before enabling production TLS.

The current Stalwart configuration uses automatic certificates with TLS-ALPN-01 and exposes its HTTPS listener through NodePort `30443`.

TLS-ALPN-01 requires the ACME server to reach Stalwart on public TCP 443 and negotiate `acme-tls/1`; a proxy that terminates or drops that negotiation breaks issuance ([Stalwart challenge documentation](https://stalw.art/docs/server/tls/acme/challenges/)).

Choose and record one complete design:

- Give Stalwart direct layer-four ownership of TCP 443 and place application HTTPS elsewhere.
- Use a TLS proxy that can route the required ALPN connection to Stalwart and route application names correctly.
- Change Stalwart to DNS-01 or another supported challenge and let the application proxy own TCP 443.
- Terminate Stalwart TLS at the edge and manage its certificates under that design.

Do not deploy competing TCP 443 forwards.

### Mail edge and DNS

Forward only the mail ports required by the accepted client and delivery design.

The current manifests expose SMTP 25, submissions 465, submission 587, IMAPS 993, and HTTPS 443 through fixed NodePorts.

Publish and verify all of these records:

- A and AAAA for the mail hostname.
- PTR for each sending address where the network provider supports it.
- MX for each receiving domain.
- SPF authorizing the actual outbound path.
- DKIM public keys matching Stalwart's active selectors.
- DMARC policy and report destination.

Stalwart's setup documentation explains the roles of [MX, SPF, DKIM, and DMARC records](https://stalw.art/docs/install/dns/).

The repository configures DNS and certificate management as manual in Stalwart, so publishing these records remains operator work.

The configured outbound route depends on the external `inbox.eu` SMTP relay and its credentials, availability, limits, and policy.

### External acceptance

Do not declare the public integration complete until all applicable checks pass from outside the home network:

- Resolve every public hostname over the intended address families.
- Validate each TLS chain, hostname, protocol, and renewal path.
- Confirm WebSocket upgrades through the application proxy.
- Sign in to OpenCloud, OnlyOffice, Grist, AFFiNE, and mail endpoints.
- Create, edit, save, close, and reopen an office document.
- Confirm concurrent office editing if it is an accepted requirement.
- Deliver mail locally between managed mailboxes.
- Receive mail from an unrelated external provider.
- Relay mail to an unrelated external provider through inbox.eu.
- Verify the forwarding-domain alias reaches its primary mailbox.
- Verify SPF, DKIM, and DMARC results in received-message headers.

## Failure boundary

This design has one storage host, one RAIDZ1 vdev, one PostgreSQL instance, local persistent volumes, and a combined k0s controller and worker.

Any host, pool, controller, or PostgreSQL outage can affect every service.

RAIDZ1 is a [single-parity layout](https://openzfs.github.io/openzfs-docs/man/master/7/zpoolconcepts.7.html) that tolerates one unavailable member in the vdev, but it is not a host-level availability mechanism or a backup.

The automation fixes RAIDZ1 as the pool topology, so production acceptance requires a written rationale in the deployment records.

Do not accept RAIDZ1 until its single-parity exposure and expected resilver time fit the recorded RPO and RTO.


## PostgreSQL durability and upgrades

The PostgreSQL manifest sets `full_page_writes=off`, uses an 8 KiB ZFS record size, and initializes the cluster with data checksums disabled.

Disabling full-page writes assumes that the direct ZFS storage path provides atomic PostgreSQL page writes across crashes.

PostgreSQL normally uses full-page writes to protect against torn pages, and its documentation warns that disabling them can cause unrecoverable corruption after a system failure ([PostgreSQL WAL settings](https://www.postgresql.org/docs/current/runtime-config-wal.html)).

Re-enable `full_page_writes` before moving PostgreSQL through a storage layer whose 8 KiB atomicity has not been established.

Disabled data checksums are a separate loss of corruption detection and are not justified by the full-page-write assumption; PostgreSQL provides [`pg_checksums`](https://www.postgresql.org/docs/current/app-pgchecksums.html) to manage and verify them on a stopped cluster.

Record and periodically review both decisions.

## Capacity contract

Each service PV advertises `10Ti` as a stable Kubernetes allocation contract.

The service dataset's ZFS quota enforces its actual storage limit and can be far smaller than `10Ti`.

The shared PostgreSQL dataset quota includes every application database, WAL, indexes, and maintenance headroom.

The operator must assign and monitor a database budget for Grist, AFFiNE, Stalwart, Zabbix, and PostgreSQL administration within that shared quota.

Before enabling stages, reserve capacity for:

- The operating system and system processes.
- k0s, kubelet, and container runtime processes.
- ZFS ARC.
- Kubernetes workload requests and initialization Jobs.
- CPU peaks during indexing, extraction, office conversion, and recovery.
- Container images and unpacked image layers.
- Container logs and application logs.
- Uploads, office conversions, Tika extraction, and other temporary data.
- ZFS snapshots and replication staging.
- PostgreSQL WAL, vacuum, reindex, and major upgrades.

Reject a configuration whose summed reservations and operating headroom exceed the host.

Alert before any dataset, pool, log filesystem, image store, or temporary-data area reaches its stop-work threshold.

## Self-hosting boundary

Outbound Stalwart delivery depends on the configured inbox.eu account and network access to its relay.

OpenCloud downloads its Draw.io extension from GitHub during initialization when the pinned extension is absent.

The installed OpenCloud app configuration uses the remote editor at `https://embed.diagrams.net`, so Draw.io editing also depends on that external service and outbound network access.

Cache or mirror required artifacts and replace the remote editor when recovery must work without their public sources.

Record account ownership, billing or renewal dates, rate limits, credential recovery, and support paths for each external service.

The absence of a repository license is unresolved and must not be interpreted as permission to redistribute the code.

## Monitoring contract

The in-cluster Zabbix deployment shares the same host, pool, cluster, and PostgreSQL failure boundary as the services it observes.

Provide an external heartbeat and notification route that remain available during a total host outage.

Monitor at least:

- Public HTTPS, mail submission, and IMAPS reachability.
- External heartbeat age.
- Backup completion and recovery-point age.
- Independent-destination replication lag.
- Certificate expiry and renewal failures.
- Pool health, scrub results, and unavailable telemetry.
- Dataset and pool capacity.
- Workload readiness and restart loops.
- PostgreSQL availability and shared-quota growth.
- Last successful restore exercise age.
- Offline recovery-copy review age.

An alert is not operational until the recorded notification destination receives and acknowledges a forced test event.

A backup is not restore-ready until an isolated restore exercise proves that its data, keys, cluster state, instructions, and software artifacts are sufficient within the recorded RTO.
