# VMware installation acceptance

This run uses an ephemeral Ubuntu 26.04 VMware Workstation guest with 20GiB RAM and two unused 40GiB data disks.

## Environment

- The operating system remains on `/dev/sda`.
- The installer selects `/dev/sdb` and `/dev/sdc` through their existing PCI/SCSI paths.
- `tank` uses one two-disk RAIDZ1 vdev with approximately 38.5GiB usable capacity.
- The test domain is `private-cloud.test`.
- Intel GPU acceleration requires a separate hardware acceptance run.
- The host ZFS ARC is capped at 1GiB for this run.
- Generated credentials remain outside the repository or in Ansible Vault ciphertext.
- Local mock credentials and artifacts persist under root-only `/var/lib/private-cloud-live-test`.

## Live failures corrected

| Failure | Correction | Evidence |
| --- | --- | --- |
| VMware supplies no disk serial IDs. | Prefer `by-id` and fall back to existing `by-path` symlinks. | Both selected 40GiB disks passed the installer's whole-disk safety checks. |
| Ansible rejects Kubernetes memory units such as `1Gi`. | Reuse the installer's RAM conversion through an Ansible filter. | Preflight passed after the correction. |
| Pool creation treats `cachefile` as a filesystem property. | Use the pool-property option `-o`. | The installer created an online RAIDZ1 pool. |
| Native key units remain inactive after direct dataset creation. | Start the generated key unit before validating mounts. | Encrypted datasets remain mounted after systemd reload. |
| PostgreSQL expects pgvector 0.8.1 but its pinned image contains 0.8.2. | Keep the expected extension version aligned with the pinned image. | Live `pg_available_extensions` reports vector 0.8.2 and VectorChord 1.1.1. |
| Missing k0s unit returns a nonzero discovery status. | Accept the missing-unit status during initial service discovery. | The installer installed and started the controller service. |
| Mount validation rejects native `BindsTo` key dependencies. | Accept `BindsTo` or `Requires` with ordering after key loading. | The encrypted-mount checker passed against OpenZFS 2.4.1 generated units. |
| Existing PV checks treat YAML `values` keys as dictionary methods. | Use explicit bracket lookup for node selector values. | Live reapplication reached networking after the correction. |
| New service datasets are absent from the native mount generator cache. | Refresh the ZFS mount inventory after all roles finish. | Final validation will recheck every generated encrypted mount unit. |
| Manticore's default SQL HTTP mode rejects `SELECT 1` with HTTP 501. | Use `POST /sql?mode=raw` with a plain SQL body. | The role validator returned HTTP 200 for `SELECT 1`. |
| OnlyOffice's namespace validator could not read PID 1's proc entries and selected a terminating pod during rollout. | Inspect `/proc/self` in the exec process and select only a Ready, non-terminating pod. | Reapply confirmed `hostUsers: false`, a distinct user namespace, and UID map `0 3595239424 65536`. |
| Grist rejects a valid configured administrator email. | Use Python's whitespace regex instead of POSIX character classes. | The corrected assertion accepts the configured trial address. |
| Grist's HTTP probe followed the configured HTTPS home URL to an HTTP-only container port, then kubelet restarted it. | Probe Grist's `/status` endpoint for startup, readiness, and liveness. | The pinned health route returned HTTP 200 with `is alive`; the patched Deployment rolled out Ready with no restarts. |

## Network startup findings

- The pinned AmneziaWG compatibility wrapper passed the wrong socket type to Ubuntu Linux 7.
- The role now matches each UDP function wrapper to its installed header signature.
- Direct DKMS build, installation, and module loading passed after the correction.
- Kubernetes rejected the VPN pod's unapproved forwarding sysctl.
- The worker profile now allowlists only the namespaced `net.ipv4.ip_forward` setting.
- A k0s startup race required waiting for its published profile before restarting a stale worker.
- AmneziaWG then reached a ready state with its interface and firewall rules active.
- Media's protocol assertion returned text instead of an Ansible boolean.
- Traefik replacement pods could not reserve ports held by the old pod.
- A `Recreate` deployment strategy allowed the replacement Traefik pod to start.
- The local CA validates HTTPS through Traefik using configured test hostnames.
- The actual DDNS CronJob created all ten configured A records through the local HTTPS Cloudflare mock.
- Traefik needs egress to the API server's discovered endpoint address after service translation.
- Traefik's Kubernetes provider needs Node read permissions before its informer caches can sync.
- Both fixes restored routing to the installed mail and media backends.

## Media startup findings

- All four ARR deployments reached ready states.
- A proxy-port readiness check incorrectly marked a disconnected Gluetun gateway ready.
- Explicit startup capabilities and a VPN health probe corrected the false readiness result.
- The gateway then created `tun0` and completed an authenticated OpenVPN connection.
- Jellyfin requires at least 2GiB free in its data directory at startup.
- This run raised the shared media dataset quota setting from 1G to 3G.
- Readiness retries now tolerate a transient unavailable Kubernetes API result.

## Mail startup findings

- Stalwart's service selector included its configuration job as a backend.
- Both mail service selectors now require the server component label.
- Configuration job waiting now honors Kubernetes retries before reporting terminal failure.
- The CLI started before kube-router finished applying its pod network policies.
- A TCP readiness init container allowed the same CLI image to retrieve its schema successfully.
- The real ACME provider rejected the reserved `.test` contact domain during account registration.
- A local ACME endpoint now exercises account registration and CSR signing with configured hostnames.
- Its domain ownership challenges and JWS verification are mocked.
- Stalwart rejected an empty automatic DNS record set; the TLS domain now requests CAA publishing.
- Real Cloudflare publishing rejected the mock token before scheduling certificate issuance.
- A supported explicit renewal task issued a trusted mail certificate through the local ACME server.
- Traefik PROXY metadata made the default port-based authentication rule reject inbound mail.
- Traefik now preserves destination port 25 with a matching internal entrypoint.
- Stalwart's port-aware authentication defaults have been restored and verified through its API.
- The SMTP validator accepts the configured forwarding recipient and rejects anonymous external relaying.
- Stalwart now waits for PostgreSQL DNS and TCP readiness before starting.

## Current base service measurements

| Service | Configured memory cap | Idle memory observed |
| --- | --- | --- |
| PostgreSQL | 1GiB | 61MiB |
| Meilisearch | 256MiB | 33MiB |
| Tika | 512MiB | 212MiB |
| Manticore | 256MiB | 63MiB |
| Redis for AFFiNE | 128MiB | 17MiB |

These readings show this run's idle footprint; they do not establish production minimums.

## Base application probes

- PostgreSQL accepted TCP `SELECT 1` and reported the expected pgvector and VectorChord versions.
- Authenticated Meilisearch index listing, Tika text extraction, Manticore raw SQL `SELECT 1`, and Redis AFFiNE SET/GET/DEL all passed against the live services.

## Application startup findings

- Grist's `/` redirected kubelet's HTTP probe to the configured HTTPS boot URL, but the container listener serves HTTP.
- Using the pinned image's `/status` health route stopped probe-driven restarts and passed the service validator.
- OnlyOffice booted with a 2GiB cap and used roughly 960MiB during startup.
- Its WOPI discovery and isolated user namespace checks passed independently.
- OpenCloud exposed insufficient schedulable ephemeral storage with the initial 3G quota.
- The VM trial increases the shared ephemeral quota to 8G before continuing.
- OpenCloud's POSIX driver requires `nats-js-kv` for its file-ID cache.
- Replacing the incompatible memory cache allowed OpenCloud to reach Ready without restarts.
- A snapshot and archive preserve a broken generated OpenCloud metadata directory from the interrupted first boot.
- Regenerating that directory removed its storage metadata errors.
- OpenCloud initialization now propagates first-boot failures instead of ignoring every exit status.

## Acceptance status

The installation and service validation are still in progress.

The guest was rebooted during the run.

The encrypted pool, native mounts, k0s, and previously installed service data survived.

Stalwart retried startup after a temporary PostgreSQL DNS lookup failure.

The local external mocks required restoration because their original files lived under `/run`.

Mock artifacts now persist in a root-only directory, with stale PID files discarded after each reboot.

The installer is reapplying the repaired networking and mail configuration before continuing to the applications.

Local OpenVPN, HTTPS Cloudflare API, ACME, and TLS SMTP relay mocks are running for external integration checks.
