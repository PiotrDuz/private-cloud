1. Review scope
    - Reviewed the current working tree on 2026-09-02, including uncommitted service additions.
    - Read all repository Markdown files and sampled every implemented step in PLAN.md.
    - Inspected installer flow, role tasks, templates, Kubernetes manifests, and monitoring collectors.
    - Findings describe source behavior without running installation, changing infrastructure, or exercising live services.
    - PLAN.md remains unchanged.

2. Design worth keeping
    - One host runs encrypted ZFS storage and a combined k0s controller and worker.
    - Native ZFS mount units establish the storage dependency before k0s starts.
    - Backup and disposable data have separate dataset branches.
    - Service datasets have explicit quotas and dedicated retained 10Ti local volumes.
    - PostgreSQL is shared, with separate application databases and login roles.
    - Vault holds configuration secrets and temporary cluster credentials are cleaned up.
    - Plain Kubernetes YAML is a good review interface when deployment consumes those exact files.

3. Source-confirmed errors
    1. [P1] Preflight puts task keywords inside assertion arguments.
        - Eighteen assertions nest `loop`, `when`, or `no_log` under `ansible.builtin.assert` in [preflight tasks](ansible/roles/preflight/tasks/main.yml).
        - The encrypted-schema assertion already contains an unsupported `no_log` argument before any installation stage runs.
        - Nested loops do not define `item`, and nested conditions and logging controls do not act as task keywords.
        - Move these keys beside the module, following the [assert parameters](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/assert_module.html) and [task keywords](https://docs.ansible.com/projects/ansible/latest/reference_appendices/playbooks_keywords.html).
    2. [P1] Several advertised secret rotations cannot converge.
        - [The installer](ansible/install.py) offers storage, PostgreSQL administrator, and Zabbix administrator rotation and saves new ciphertext before applying it.
        - [ZFS](ansible/roles/zfs/tasks/main.yml) validates the new passphrase against the existing key without performing a key change.
        - [PostgreSQL](ansible/roles/postgres/tasks/main.yml) rejects a changed administrator password against the existing Secret.
        - [Zabbix authentication](ansible/roles/zabbix_server/tasks/api_auth.yml) tries the new password and factory password without retaining the current password.
        - Preserve previous credentials until each service has changed and verified its credentials, with explicit recovery for partial completion.
        - Temporarily reject unsupported rotations before saving configuration.
    3. [P1] Optional services break host monitoring on a fresh installation.
        - [The ZFS collector](zabbix/zabbix-zfs-collector.py) queries every hardcoded service dataset regardless of enabled stages.
        - A missing optional dataset increases `error_count`, which [the agent role](ansible/roles/zabbix_agent/tasks/main.yml) requires to equal zero.
        - Derive expected datasets from enabled services and distinguish disabled storage from missing required storage.
        - Use the same inventory for dashboard items and dataset alerts.
    4. [P1] The SMART wrapper does not constrain privileged commands.
        - [The wrapper](zabbix/zabbix-smartctl-wrapper) forwards every argument to root-owned `smartctl` without validation.
        - [The sudoers template](ansible/roles/zabbix_agent/templates/sudoers.j2) allows additional arguments after `-a` through a wildcard.
        - An appended `--smart=off` can change device settings on supported drives, according to the [smartctl manual](https://github.com/smartmontools/smartmontools/blob/main/src/smartctl.8.in).
        - Sudo matches argument wildcards across the argument string, including whitespace, as documented in the [sudoers manual](https://www.sudo.ws/docs/man/1.9.14/sudoers.man.pdf).
        - Validate exact read-only command forms and device paths inside the Python wrapper.
    5. [P1] The first reapply after reboot can report completion without applying services.
        - [The ZFS role](ansible/roles/zfs/tasks/main.yml) executes `meta: end_play` after successful boot verification.
        - This skips subsequent roles while [the installer](ansible/install.py) still returns `status: completed`.
        - An update immediately after reboot can therefore save new desired state without applying it.
        - Continue convergence after verification or expose a separate verification result, since [end_play ends the entire play](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/meta_module.html).
    6. [P2] Kubernetes bases and deployed manifests are independent sources.
        - Service roles use `lookup('template', ...)` and never read `k0s-services/*/kustomize/base`.
        - [The PostgreSQL base PV](k0s-services/postgres/kustomize/base/persistent-volume.yaml) points to `/var/lib/private-cloud/postgres`, while Ansible uses the ZFS service dataset.
        - [The Zabbix base PV](k0s-services/zabbix/kustomize/base/persistent-volume.yaml) similarly points to `/var/lib/zabbix`.
        - PostgreSQL's base requests `512Mi` while the example configuration deploys `2Gi`.
        - Editing reviewed Kubernetes YAML currently has no effect on an installer deployment.
    7. [P2] Changing the configured k0s version has no effect on an existing binary.
        - [The k0s role](ansible/roles/k0s/tasks/main.yml) only installs when the binary is absent and never compares its version.
        - Reject version mismatches or provide an explicit upgrade operation.
    8. [P2] Configuration evolution blocks the Update workflow.
        - [The installer](ansible/install.py) validates existing configuration before allowing a lifecycle choice.
        - [The schema validation](ansible/install_helpers.py) requires exact service sections and stage keys.
        - An older configuration missing newly added services cannot reach Update to acquire them.
        - Add a schema version and an explicit migration before strict validation.
    9. [P2] Installer failures lose the useful Ansible output.
        - [run_command](ansible/install_helpers.py) captures stdout while exposing only stderr on failure.
        - Failed-task details and the play recap can disappear from the installer result.
        - Return a sanitized failed stage, task, and error while keeping detailed logs root-only.
    10. [P2] The documented command does not select the repository Ansible configuration.
        - [run_playbook](ansible/install.py) neither changes directory nor sets `ANSIBLE_CONFIG`.
        - Running from the repository root leaves [ansible/ansible.cfg](ansible/ansible.cfg) outside normal [configuration discovery](https://docs.ansible.com/projects/ansible/latest/reference_appendices/config.html).
        - Set its absolute path explicitly so local machine defaults cannot change installer behavior.
    11. [P2] Most rollout checks can accept status from the previous deployment generation.
        - [Tika](ansible/roles/tika/tasks/main.yml), [OpenCloud](ansible/roles/opencloud/tasks/main.yml), and several other roles check replica counts without checking `observedGeneration`.
        - An immediate read after an update can still describe the previous healthy workload.
        - Reuse PostgreSQL's generation check and require readiness for the intended revision.

4. Coverage of PLAN.md

    | Step | Sampled implementation | Finding |
    | --- | --- | --- |
    | 1. ZFS | [Tasks](ansible/roles/zfs/tasks/main.yml), key handling, scrub units | Strong disk guards and boot checks; rotation and restore need explicit lifecycles. |
    | 2. k0s | [Tasks](ansible/roles/k0s/tasks/main.yml), mount dependency template | Runtime data is separated; version convergence and recovery are incomplete. |
    | 3. PostgreSQL | [Tasks](ansible/roles/postgres/tasks/main.yml), Deployment, pgvector Job | Tuning and vector verification exist; administrator rotation and backup are incomplete. |
    | 4. Zabbix | [Server role](ansible/roles/zabbix_server/tasks/main.yml), agent, collectors, alerts, dashboard | Optional datasets break monitoring; notification delivery is not configured. |
    | 5. Meilisearch | [Tasks](ansible/roles/meilisearch/tasks/main.yml), Deployment, Secret handling | Storage and key changes are implemented; document index recovery and upgrades. |
    | 6. Stalwart | [Tasks](ansible/roles/stalwart/tasks/main.yml), StatefulSet, configuration Job | Domain and relay setup exist; verification stops at cluster endpoints. |
    | 7. Tika | [Tasks](ansible/roles/tika/tasks/main.yml), Deployment | The stateless extractor has a policy-driven PV; document the purpose of retained data. |
    | 8. Bleve | [Tasks](ansible/roles/bleve/tasks/main.yml), PV and PVC | Correctly provisions embedded OpenCloud search storage without a separate server. |
    | 9. OnlyOffice | [Tasks](ansible/roles/onlyoffice/tasks/main.yml), Deployment | WOPI discovery is checked; public TLS and document save behavior remain unverified. |
    | 10. OpenCloud | [Tasks](ansible/roles/opencloud/tasks/main.yml), Deployment, ConfigMaps | Tika, Bleve, collaboration, and Draw.io are wired; external HTTPS routing remains manual. |
    | 11. Grist | [Tasks](ansible/roles/grist/tasks/main.yml), Deployment | Metadata, documents, and Pyodide are configured; document the completed login setup. |
    | 12. Manticore | [PLAN.md](PLAN.md) versus [site.yml](ansible/site.yml) | No role, stage, dataset, PV, or service manifest exists. |
    | 13. AFFiNE | [Tasks](ansible/roles/affine/tasks/main.yml), Redis, migration Job | PostgreSQL and Redis exist; the planned Manticore indexer configuration is absent. |

5. Architecture improvements
    1. Define backup and restore before storing irreplaceable data.
        - The `backup` branch currently names eligible data without scheduling snapshots, replication, or recovery.
        - Specify retention, an independent backup destination, and acceptable data loss and recovery time.
        - Restore PostgreSQL metadata and associated Stalwart, Grist, and AFFiNE files from a coordinated recovery point.
        - Keep recoverable copies of Vault ciphertext, encryption credentials, and host bootstrap configuration outside this host.
        - Document protection of `/etc/zfs/keys/tank-secure.key`, which enables automatic unlock from the host filesystem.
        - Include k0s control-plane recovery separately from application volumes, using its [backup and restore support](https://docs.k0sproject.io/stable/backup/).
    2. Make public networking a first-class stage.
        - Specify DNS, TLS termination, renewal, firewall rules, WebSockets, and access to public hostnames from pods.
        - Define ownership of public port 443 between application HTTPS and Stalwart TLS-ALPN-01.
        - Give mail its required TCP forwarding and document MX, SPF, DKIM, and DMARC configuration.
        - Verify mailbox access, local delivery, relay delivery, forwarding aliases, and office document saves before declaring integration complete.
    3. Declare the supported host and dependency versions.
        - [PostgreSQL defaults](ansible/roles/postgres/defaults/main.yml) require the dataset `prefetch` property documented in [OpenZFS 2.3](https://openzfs.github.io/openzfs-docs/man/v2.3/7/zfsprops.7.html).
        - [OpenZFS 2.2](https://openzfs.github.io/openzfs-docs/man/v2.2/7/zfsprops.7.html) lacks that property, so the broad Ubuntu/Debian prerequisite permits incompatible hosts.
        - Check required kernel, ZFS, Ansible, and collection capabilities before creating storage.
        - Pin collection versions, release artifacts, and image digests, including the currently unpinned Stalwart CLI.
    4. Budget the whole host.
        - The example configuration requests 20.5Gi across configured application containers before Zabbix, migration Jobs, Kubernetes, and host overhead.
        - Zabbix containers and migration Jobs currently lack resource budgets.
        - Reserve memory for ZFS ARC and system processes before accepting application requests.
        - Budget CPU, temporary extraction data, container logs, and image storage alongside persistent datasets.
        - Explain that 10Ti is the Kubernetes allocation contract while the ZFS quota enforces actual storage use.
        - Account for each application database within the shared PostgreSQL quota separately from its file dataset.
    5. Define the single-host failure boundary.
        - RAIDZ1, one PostgreSQL instance, and local PVs leave all services dependent on this host.
        - Bind volumes to the managed storage host instead of selecting an arbitrary Ready node independently in each role.
        - Document disk replacement, host replacement, pool import, PV rebinding, and recovery order.
        - Record why RAIDZ1 suits the chosen disks and recovery requirements.
    6. Isolate workloads using reviewable Kubernetes policies.
        - The shared namespace currently has no NetworkPolicy resources or workload-specific service accounts.
        - Add explicit allowed connections for PostgreSQL, search, extraction, mail administration, and public applications.
        - Disable service-account token mounting where Kubernetes API access is unnecessary.
        - Apply non-root execution and reduced capabilities where application images support them.
        - Validate enforcement through the configured network plugin, following [NetworkPolicy behavior](https://kubernetes.io/docs/concepts/services-networking/network-policies/).
    7. Preserve the reason behind PostgreSQL durability settings.
        - `full_page_writes=off` is defensible for direct ZFS storage with sufficient record atomicity, according to the [PostgreSQL explanation](https://wiki.postgresql.org/wiki/Full_page_writes).
        - Record that assumption beside the setting and revisit it when the storage path changes.
        - Treat disabled database checksums as a separate decision about corruption detection.
        - Define major-version migrations and recovery before changing the PostgreSQL image family.
    8. Make application upgrades and restarts deliberate.
        - Add startup probes so long recovery does not trigger liveness restarts, following [Kubernetes probe semantics](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
        - Define failed migration recovery and schema compatibility with the previously running AFFiNE version.
        - Keep migration Job identity tied to the actual migration revision.
        - Replace Stalwart's timestamp-driven reprovisioning on every reapply with configuration-driven changes where supported.
        - Retain temporary recovery access cleanup while avoiding unnecessary mail restarts.
    9. Complete monitoring outside the failure boundary.
        - Zabbix currently depends on the same host, pool, cluster, and PostgreSQL that it monitors.
        - Add an external heartbeat and a configured notification destination.
        - Monitor backup freshness, certificate expiry, unavailable workloads, and restore readiness.
        - Distinguish unavailable SMART or ECC telemetry from a healthy device.
    10. Define the self-hosting boundary.
        - inbox.eu delivery and the remote Draw.io editor are explicit external service dependencies.
        - Document which functions require external accounts or network access.
        - Add a repository license and concise contributor instructions for the intended open-source project.

6. Make review follow the deployed files
    1. Make `k0s-services/<service>/kustomize/base` the authoritative workload definition.
    2. Have Ansible generate small site patches for hostnames, NodePorts, memory, and local-volume node affinity.
    3. Use Kustomize's existing [patches and image transformations](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/) to combine those values with the base.
    4. Keep Secret creation separate and expose only Secret references in public review artifacts.
    5. Apply the rendered Kubernetes objects that reviewers inspect.
    6. Remove duplicate full manifests from role templates after switching their consumers.
    7. Preserve explicit storage, database bootstrap, migration, deployment, and readiness ordering in each service role.
    8. Extract repeated kubeconfig, dataset, database-role, and rollout operations into small shared task files.
    9. Keep service-specific behavior visible instead of building a generic application deployment framework.
    10. Move long shell programs into focused Python helpers and keep SQL and application configuration in native files.
    11. Extend the native-file approach to Stalwart configuration plans and Zabbix API request bodies.
    12. Define service dependencies and dataset metadata once for installer prompts, preflight, and monitoring.
    13. Provide deterministic non-secret rendered manifests as review artifacts without requiring root or a cluster.
    14. Use YAML parsing, Ansible linting, and Kubernetes schema validation to catch structural mistakes before installation.
    15. Keep PLAN.md as short architecture decisions and place operation details in service READMEs.

7. Suggested implementation order
    1. Fix preflight, unsafe SMART arguments, broken rotations, and misleading completion results.
    2. Make optional stages work with monitoring and preserve useful installer failure details.
    3. Switch one small service such as Tika to authoritative YAML plus narrow patches.
    4. Extend that pattern to the remaining services and remove duplicate manifests.
    5. Add backup, restore, public networking, and dependency compatibility contracts.
    6. Complete Manticore integration and document supported upgrade procedures.
