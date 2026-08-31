# Ansible migration plan

## Goal

Replace the current installation workflow with one interactive Python entry point and one unattended Ansible playbook.

Python will request all installation values before the playbook starts.
Python will validate prompt formats before writing the configuration.
Ansible will validate the complete configuration before changing the host.
The Ansible run will not ask questions between stages.

## Target behavior

- One Python session will collect the complete private-cloud configuration.
- One persistent YAML file will store non-secret configuration.
- One persistent Vault file will store encrypted secrets.
- One preflight role will validate every configuration value.
- One playbook will run all enabled stages in dependency order.
- Stage selection will be declared in the configuration file.
- Every role will be safe to rerun after a successful installation.
- Failed runs will resume through Ansible idempotence.
- Sensitive tasks will use `no_log: true`.
- Runtime collectors will remain Python assets.
- The Python entry point will manage configuration, invoke Vault, and invoke Ansible.
- Replaced stage-specific Python installers will be removed after migration.
- Native OpenZFS systemd mount generation will be mandatory.
- The installer will not provide a mount fallback.
- Operating-system and OpenZFS upgrades will require a supervised run.
- The migration will target a fresh host instead of adopting an earlier installation.

The complete installation will start with `sudo python3 ansible/install.py`.
The Python entry point will require root and an interactive terminal.
No configuration prompts will appear after Ansible starts.

## Proposed repository structure

```text
ansible/
  ansible.cfg
  install.py
  install_helpers.py
  site.yml
  requirements.yml
  config/
    private-cloud.example.yml
    private-cloud.yml
    private-cloud.secrets.yml
  inventory/
    hosts.yml
  roles/
    preflight/
      tasks/main.yml
    zfs/
      defaults/main.yml
      handlers/main.yml
      tasks/main.yml
      templates/
    k0s/
      defaults/main.yml
      handlers/main.yml
      tasks/main.yml
      templates/
    postgres/
      defaults/main.yml
      tasks/main.yml
      templates/
    zabbix_server/
      defaults/main.yml
      tasks/main.yml
      tasks/api.yml
      tasks/database.yml
      templates/
    zabbix_agent/
      defaults/main.yml
      handlers/main.yml
      tasks/main.yml
      templates/
```

`private-cloud.example.yml` will document both configuration contracts.
It will contain placeholders and safe defaults only.
`private-cloud.yml` will contain readable non-secret configuration.
`private-cloud.secrets.yml` will contain only Ansible Vault ciphertext.
Both persistent files may be version controlled.
The Vault password must never be committed with them.

## Configuration loading

`install.py` will pass both configuration files to `ansible-playbook` as extra-vars files.
`install.py` will supply the Vault password without placing it in process arguments.
The playbook will not read installation settings from environment variables.
Role defaults will define implementation constants only.
Persistent desired-state values will come from the two configuration files only.
Destructive authorization will come from the active interactive session only.
Role defaults will not supply missing quota or PostgreSQL memory values.

The inventory will contain Ansible connection details only.
The application configuration will not be split across inventory variables.

## Interactive configuration

1. Run `sudo python3 ansible/install.py` from the repository root.
2. Choose to create, update, reapply, or rotate the configuration.
3. Select every stage before a new installation starts.
4. Answer the prompts for values that are being created or changed.
5. Review the sanitized configuration summary.
6. Enter the destructive ZFS confirmation when ZFS creation is selected.
7. Confirm that Ansible may start.

Each prompt will show the expected format and a safe default when one exists.
Disk selection will show stable device IDs with their model and capacity.
Secret prompts will hide input and require confirmation.
The Vault password prompt will hide input.
Invalid values will be explained and requested again.
The Python entry point will write configuration only after all prompts pass validation.
Reapply will preserve the existing configuration without asking for every value again.
The playbook run will not ask for individual installation values.

## Configuration lifecycle

1. Create `/run/private-cloud` as a root-owned directory with mode `0700`.
2. Acquire a lock that prevents concurrent installer sessions.
3. Write `private-cloud.yml` atomically without secret values.
4. Create a plaintext secrets file under `/run` when secrets are created or changed.
5. Create a temporary Vault-password file under `/run` with mode `0600`.
6. Ask `ansible-vault` to create a temporary encrypted output file.
7. Validate and atomically replace `private-cloud.secrets.yml` with the encrypted output.
8. Delete the plaintext secrets file immediately after encryption.
9. Run `ansible-playbook` with the public and encrypted files.
10. Delete the Vault-password file in a `finally` block.

Plaintext secrets will exist in a temporary file only while Vault creates or updates the encrypted file.
The Vault password will exist in a temporary file only while Vault or Ansible needs it.
Temporary files will use `/run` so normal Linux installations keep them on a memory-backed filesystem.
The entry point will reject an unsafe or symbolic-link runtime directory.
The entry point will remove its own stale files from interrupted earlier sessions.
A reboot will clear files from the normal `/run` filesystem.
An uncatchable termination may leave a file until the next installer run or reboot.
The entry point will not print plaintext secret values.

## Public configuration contract

```yaml
private_cloud:
  stages:
    zfs: true
    k0s: true
    postgres: true
    zabbix_server: true
    zabbix_agent: true

  storage:
    disks:
      - /dev/disk/by-id/replace-with-first-disk
      - /dev/disk/by-id/replace-with-second-disk

  k0s:
    version: v1.36.2+k0s.0
    config_quota: 1G
    images_quota: 10G
    ephemeral_quota: 10G

  postgres:
    volume_size: 20G
    max_ram: 2Gi

  zabbix:
    storage_size: 5G
    database_name: zabbix
    database_username: zabbix
    server_node_port: 31051
    web_node_port: 30080
    hostname: private-cloud-zabbix
    admin_username: Admin
    agent_server_active: 127.0.0.1:31051
```

## Encrypted secrets contract

The decrypted content of `private-cloud.secrets.yml` will use this structure.

```yaml
private_cloud_secrets:
  storage:
    encryption_passphrase: replace-with-zfs-passphrase
  postgres:
    admin_password: replace-with-postgres-password
  zabbix:
    database_password: replace-with-zabbix-database-password
    admin_password: replace-with-zabbix-admin-password
```

The stored file will contain Vault ciphertext instead of readable YAML.

## Runtime authorization

The `CREATE tank` confirmation will not be stored in either persistent file.
Python will request it only when the pool is absent and ZFS creation is enabled.
Python will pass it to Ansible as `private_cloud_runtime.storage_create_confirmation`.
Ansible will validate it immediately before the destructive block.

## Configuration mapping

| Current input | Ansible variable | Default | Secret |
|---|---|---:|:---:|
| Stage run or skip | `private_cloud.stages.*` | `true` | No |
| Selected ZFS disks | `private_cloud.storage.disks` | None | No |
| ZFS passphrase | `private_cloud_secrets.storage.encryption_passphrase` | None | Yes |
| ZFS confirmation | `private_cloud_runtime.storage_create_confirmation` | None | No |
| `K0S_VERSION` | `private_cloud.k0s.version` | `v1.36.2+k0s.0` | No |
| `K0S_CONFIG_QUOTA` | `private_cloud.k0s.config_quota` | `1G` | No |
| `K0S_IMAGES_QUOTA` | `private_cloud.k0s.images_quota` | `10G` | No |
| `K0S_EPHEMERAL_QUOTA` | `private_cloud.k0s.ephemeral_quota` | `10G` | No |
| `POSTGRES_VOLUME_SIZE` | `private_cloud.postgres.volume_size` | `20G` | No |
| `POSTGRES_MAX_RAM` | `private_cloud.postgres.max_ram` | `2Gi` | No |
| `POSTGRES_ADMIN_PASSWORD` | `private_cloud_secrets.postgres.admin_password` | None | Yes |
| `ZABBIX_STORAGE_SIZE` | `private_cloud.zabbix.storage_size` | `5G` | No |
| `ZABBIX_DB_NAME` | `private_cloud.zabbix.database_name` | `zabbix` | No |
| `ZABBIX_DB_USER` | `private_cloud.zabbix.database_username` | `zabbix` | No |
| `ZABBIX_DB_PASSWORD` | `private_cloud_secrets.zabbix.database_password` | None | Yes |
| `ZABBIX_SERVER_NODE_PORT` | `private_cloud.zabbix.server_node_port` | `31051` | No |
| `ZABBIX_WEB_NODE_PORT` | `private_cloud.zabbix.web_node_port` | `30080` | No |
| Zabbix host name | `private_cloud.zabbix.hostname` | `private-cloud-zabbix` | No |
| `ZABBIX_ADMIN_USERNAME` | `private_cloud.zabbix.admin_username` | `Admin` | No |
| `ZABBIX_ADMIN_PASSWORD` | `private_cloud_secrets.zabbix.admin_password` | None | Yes |
| Zabbix active server | `private_cloud.zabbix.agent_server_active` | `127.0.0.1:31051` | No |

## Fixed implementation values

These values will remain role constants unless project requirements change.

| Value | Setting |
|---|---|
| ZFS pool | `tank` |
| ZFS pool mountpoint | `/tank` |
| Encrypted root dataset | `tank/secure` |
| Encrypted root mountpoint | `/tank/secure` |
| Encryption key file | `/etc/zfs/keys/tank-secure.key` |
| Backup branch | `tank/secure/backup` |
| No-backup branch | `tank/secure/no-backup` |
| k0s configuration dataset | `tank/secure/backup/k0s/config` |
| k0s images dataset | `tank/secure/no-backup/k0s/images` |
| k0s ephemeral dataset | `tank/secure/no-backup/k0s/ephemeral` |
| Service dataset parent | `tank/secure/backup/k0s/services` |
| No-backup service dataset parent | `tank/secure/no-backup/k0s/services` |
| Kubernetes namespace | `private-cloud` |
| Service PV capacity | `10Ti` |
| PostgreSQL database | `postgres` |
| PostgreSQL administrator | `postgres` |
| PostgreSQL dataset | `tank/secure/backup/k0s/services/postgres` |
| Zabbix dataset | `tank/secure/backup/k0s/services/zabbix` |
| PostgreSQL shared buffers | Half of configured maximum RAM |
| Zabbix transport | Plaintext over localhost |
| ZFS encryption | `aes-256-gcm` |
| ZFS topology | RAIDZ1 |
| Encrypted root quota | `none` |
| Encrypted root reservation | `none` |

The ZFS pool will define the common filesystem properties for general datasets.

| Property | Setting |
|---|---|
| `acltype` | `posixacl` |
| `atime` | `off` |
| `compression` | `zstd` |
| `dnodesize` | `auto` |
| `normalization` | `formD` |
| `xattr` | `sa` |

General datasets will inherit these properties.
Only the PostgreSQL dataset will apply service-specific ZFS tuning.
Every leaf quota and PostgreSQL memory limit will come from `private-cloud.yml`.

## Upfront validation

The preflight role will complete before any modifying role starts.
Every validation will use `ansible.builtin.assert` or read-only commands.

Configuration and destructive-input validation will finish during preflight.
Runtime readiness checks will run after their prerequisite roles complete.

### General validation

- The target must be Ubuntu or Debian where currently supported.
- The Python entry point and Ansible process must run with effective UID 0.
- Every enabled stage must contain its required configuration.
- Every secret required by an enabled stage must be nonempty.
- Every stage flag must be Boolean.
- Required repository assets must exist on the controller.
- The Zabbix Agent stage requires Ubuntu.

### Dependency validation

- k0s requires the ZFS stage.
- PostgreSQL requires the k0s stage.
- Zabbix Server requires the PostgreSQL stage.
- Zabbix Agent requires the Zabbix Server stage.

### ZFS validation

- The pool name must be `tank` during the initial migration.
- The topology must be `raidz1`.
- The installed package or selected package candidate must provide `zfs-mount-generator`.
- File-based key loading must be supported.
- An existing `tank` pool before the initial installation must stop the play.

The disk wipe and pool creation block will run only during the initial installation.
The role will stop before disk modification when native mount generation is unavailable.

### ZFS creation validation

These checks will run only during the initial ZFS installation.

- At least two unique disks must be listed.
- Every disk must use a stable `/dev/disk/by-id/` path.
- Every disk path must resolve to a whole block device.
- Selected disks must not contain mounted filesystems.
- Selected disks must not contain active swap.
- Selected disks must not belong to an imported pool.
- Selected disks must not have active holders.
- The passphrase must contain between 8 and 512 bytes.
- The runtime confirmation must equal `CREATE tank`.

Python and Ansible will both validate the runtime confirmation.
A reapply of this installation will not request the confirmation.

### Size validation

- ZFS quota values must match `[1-9][0-9]*[KMGTPE]`.
- PostgreSQL RAM must use `Ki`, `Mi`, `Gi`, or `Ti`.
- PostgreSQL RAM must provide at least 128 MiB of shared buffers.
- Every leaf quota must come from the public configuration.
- A configured quota must not be reduced below used space.

Configured ZFS quota strings will be passed directly to ZFS.

### Kubernetes validation

- Both NodePorts must be between 30000 and 32767.
- The two NodePorts must differ.
- Database identifiers must use letters, digits, and underscores.
- Zabbix must not use PostgreSQL system databases.
- Zabbix must not use PostgreSQL system roles.
- The configured k0s node must report Ready.

### Zabbix validation

- The host name must be nonempty and at most 128 characters.
- The administrator name must be nonempty.
- The active server must contain a valid address and optional port.
- Template UUID values must be unique UUIDv4 values.

## Playbook flow

`site.yml` will execute the roles in the following order.

1. Load the public configuration and decrypt the Vault configuration.
2. Gather target host facts.
3. Validate the complete configuration.
4. Display a sanitized configuration summary.
5. Configure ZFS when enabled.
6. Configure k0s when enabled.
7. Deploy PostgreSQL when enabled.
8. Deploy Zabbix Server when enabled.
9. Configure Zabbix through its API.
10. Configure Zabbix Agent when enabled.
11. Run final read-only verification.
12. Print one summarized Ansible result.

The summary will replace secret values with `configured`.
The summary will list every selected disk before modification.
The playbook will not pause after printing the summary.

## Role plan

### Preflight role

- Load all variables from the configuration contract.
- Reject missing and unknown required values.
- Validate cross-stage dependencies.
- Validate native OpenZFS systemd generator capability.
- Validate disk identities when pool creation is required.
- Validate current ZFS state when ZFS creation is disabled.
- Validate NodePort and database constraints.
- Build derived dataset and mountpoint values.
- Build the sanitized installation summary.

Derived values will not be repeated in the user configuration.
Examples include service dataset names and `shared_buffers`.
The complete dataset and mountpoint layout will remain fixed role data.

### ZFS role

- Install `zfsutils-linux` and `zfs-zed` with package state `present`.
- Load the ZFS kernel module.
- Verify `zfs-mount-generator` before disk modification.
- Recheck selected disks immediately before wiping.
- Clear old ZFS labels from selected disks.
- Erase signatures from selected disks.
- Create the RAIDZ1 pool once.
- Set `ashift=12` and `autotrim=on`.
- Set `acltype=posixacl` on the pool filesystem.
- Set `atime=off` on the pool filesystem.
- Set `compression=zstd` on the pool filesystem.
- Set `dnodesize=auto` on the pool filesystem.
- Set `normalization=formD` on the pool filesystem.
- Set `xattr=sa` on the pool filesystem.
- Set `cachefile=/etc/zfs/zpool.cache` on the pool.
- Create the encrypted root dataset.
- Set root quota, refquota, reservation, and refreservation to `none`.
- Set root `keyformat=passphrase` and the fixed file key location.
- Write or recover the exact encryption key bytes without a trailing newline.
- Set the encryption key file mode to `0600`.
- Validate a recovered key against the encrypted dataset before installing it.
- Create the `backup` dataset.
- Create the `no-backup` dataset.
- Enable ZED.
- Enable the ZFS list-cache ZED hook.
- Populate `/etc/zfs/zfs-list.cache/tank`.
- Regenerate the native systemd mount and key-loading units.
- Verify the generated key unit loads `tank/secure` from its file key.
- Verify every generated mount unit depends on successful key loading.
- Remove the legacy `zfs-unlock-mount.service` unit.
- Remove the legacy `/usr/local/sbin/zfs-unlock-mount` helper.
- Enable the packaged monthly scrub timer when available.
- Install the repository scrub timer as fallback.
- Verify pool health and mounted datasets.

Pool creation will use an explicit command task because it is destructive and topology-sensitive.
Dataset property management may use the ZFS collection or guarded command tasks.
The role will fail when native generated units are missing or invalid.
The role will never install a custom mount unit as a substitute.
Package state `present` will not upgrade an existing OpenZFS installation.

### Native mount verification

- Require `/etc/zfs/zfs-list.cache/tank` to describe the encrypted root and its descendants.
- Validate the generated units before removing the legacy mount service.
- Require the generated key unit to use the configured file key.
- Require the key-loading unit before every encrypted mount unit.
- Require every k0s service path through `RequiresMountsFor`.
- Require one supervised reboot before declaring the boot path verified.
- Verify `tank/secure` reports `keystatus=available` after reboot.
- Verify every configured ZFS dataset is mounted after reboot.
- Verify k0s starts only after its ZFS mountpoints are ready.

The installer will not reboot the host automatically.
A post-reboot verification run will be read-only.

### k0s role

- Create the backup dataset hierarchy.
- Create the no-backup dataset hierarchy.
- Create `tank/secure/backup/k0s/config` with its quota.
- Create `tank/secure/no-backup/k0s/images` with its quota.
- Create `tank/secure/no-backup/k0s/ephemeral` with its quota.
- Create `tank/secure/backup/k0s/services` for service datasets.
- Create `tank/secure/no-backup/k0s/services` for no-backup service datasets.
- Mount config at `/tank/secure/k0s`.
- Mount images at `/tank/secure/k0s/containerd`.
- Mount ephemeral data at `/tank/secure/k0s/kubelet`.
- Download the configured k0s version when the binary is absent.
- Leave the installed k0s binary version unchanged during reapply.
- Generate the initial k0s configuration once.
- Install the controller and worker service once.
- Add `RequiresMountsFor` for every k0s ZFS path.
- Order k0s after the generated ZFS mount units.
- Start and enable the controller.
- Wait for the node Ready condition.
- Verify every runtime mountpoint.

General k0s datasets will inherit the common ZFS properties.
Unspecified filesystem properties will keep their inherited OpenZFS values.
The role will preserve the fixed backup and no-backup mount layout.

### PostgreSQL role

- Create the PostgreSQL service dataset.
- Apply the configured dataset quota and reservation.
- Apply the current PostgreSQL ZFS tuning.
- Resolve the Ready k0s node name.
- Render the Secret without writing plaintext to persistent files.
- Render the fixed `10Ti` PV and PVC.
- Render the PostgreSQL deployment and Service.
- Apply resources through the Kubernetes collection.
- Wait for deployment rollout.
- Wait for the PostgreSQL readiness probe.
- Verify the effective PostgreSQL settings.
- Verify the ZFS dataset properties.

The role will preserve the existing PostgreSQL image and tuning values.
The role will reject conflicting existing PV, PVC, and Secret resources.

### PostgreSQL tuning contract

- Set ZFS `recordsize=8K`.
- Set ZFS `compression=zstd`.
- Set ZFS `prefetch=none`.
- Set ZFS `primarycache=all`.
- Set ZFS `logbias=latency`.
- Set the dataset quota to the configured volume size.
- Set the dataset reservation to the configured volume size.
- Set the container memory limit to the configured maximum RAM.
- Set `shared_buffers` to half of the configured maximum RAM.
- Set `full_page_writes=off`.
- Set `wal_compression=off`.
- Set `wal_init_zero=off`.
- Set `wal_recycle=off`.
- Initialize PostgreSQL with data checksums disabled.

The role will verify every ZFS and PostgreSQL tuning value after rollout.
An existing PostgreSQL cluster with data checksums enabled will stop the play.

### Zabbix Server role

- Create or update the Zabbix PostgreSQL login role.
- Create the Zabbix database when absent.
- Preserve the configured database owner.
- Apply the Zabbix database Secret.
- Create the Zabbix service dataset.
- Apply the configured dataset quota.
- Inherit the common ZFS properties without service-specific overrides.
- Keep the inherited `recordsize` instead of applying a Zabbix override.
- Resolve the Ready k0s node name.
- Render the fixed `10Ti` PV and PVC.
- Render the server and web deployments.
- Render both NodePort services.
- Apply resources through the Kubernetes collection.
- Restart deployments only after relevant changes.
- Wait for deployments and endpoints.
- Wait for the Zabbix API.
- Bootstrap or authenticate the administrator.
- Import the repository templates.
- Create or update the host group.
- Create or update the monitored host.
- Link all required templates.
- Create or update the storage dashboard.

Zabbix API operations will use idempotent API lookups followed by `uri` calls.
API task groups will separate authentication, templates, hosts, and dashboards.
All authenticated requests will hide tokens and passwords.

### Zabbix Agent role

- Install `zabbix-agent2`, `python3`, `smartmontools`, and `sudo`.
- Load the optional `igen6_edac` module.
- Deploy the existing ZFS collector.
- Deploy the existing memory ECC collector.
- Deploy the SMART wrapper.
- Install the ZFS user parameters.
- Install the ECC user parameters.
- Install the SMART plugin configuration.
- Validate and install the sudoers rule.
- Preserve `/etc/zabbix/zabbix_agent2.conf.pre-private-cloud` once.
- Remove conflicting agent and TLS settings before installing the managed block.
- Set `Server=127.0.0.1`.
- Set `ServerActive` from `private_cloud.zabbix.agent_server_active`.
- Set `Hostname` from `private_cloud.zabbix.hostname`.
- Set `ListenIP=127.0.0.1`.
- Set `Timeout=30`.
- Set `TLSConnect=unencrypted`.
- Set `TLSAccept=unencrypted`.
- Ensure `Include=/etc/zabbix/zabbix_agent2.d/*.conf` is present.
- Enable and restart the agent through a handler.
- Verify collector JSON output.
- Verify registered agent keys.

The collector and SMART wrapper behavior will not be rewritten into Ansible.
Ansible will only install and configure these runtime assets.

The role will manage these files.

| File | Mode |
|---|---:|
| `/usr/local/libexec/zabbix/zfs-collector.py` | `0755` |
| `/usr/local/libexec/zabbix/memory-ecc-collector.py` | `0755` |
| `/usr/local/libexec/zabbix/smartctl-wrapper` | `0755` |
| `/etc/zabbix/zabbix_agent2.d/zfs.conf` | `0644` |
| `/etc/zabbix/zabbix_agent2.d/memory-ecc.conf` | `0644` |
| `/etc/zabbix/zabbix_agent2.d/plugins.d/smart.conf` | `0644` |
| `/etc/sudoers.d/zabbix-smartctl` | `0440` |

The ZFS user parameters will expose `zfs.metrics` and `zfs.snapshots`.
The ECC user parameter will expose `memory.ecc.metrics`.
The SMART plugin path will point to the managed wrapper.
The sudoers rule will permit `smartctl-wrapper -a *`.
The sudoers rule will permit `smartctl-wrapper --scan *`.
The sudoers rule will permit `smartctl-wrapper -j -V`.

### Zabbix monitoring contract

- Link the active Linux, SMART, ZFS, and memory ECC templates.
- Collect host CPU and memory performance through the Linux template.
- Collect pool health, capacity, errors, scrub state, and total size.
- Collect fixed leaf dataset usage, quota, and utilization.
- Collect SMART health and disk metrics.
- Collect corrected and uncorrected ECC counters.
- Collect snapshot counts, retained bytes, retained percentage, and age.
- Warn when tank usage exceeds 80 percent.
- Raise a high alert when tank usage exceeds 90 percent.
- Raise a high alert when a fixed leaf reaches 90 percent of its quota.
- Preserve SMART health alerts from the official active template.
- Raise a disaster alert for permanent ZFS data errors.
- Raise a high alert for unsuccessful scrub results.
- Warn for repaired scrub damage and recorded pool or vdev errors.
- Raise a disaster alert for uncorrected ECC errors.
- Warn for corrected ECC errors.
- Warn when the oldest fixed-leaf snapshot exceeds 90 days.

Snapshot retained size will be monitored without an alert threshold.
The plan does not define a large-snapshot threshold.

## Kubernetes manifest migration

The committed base manifests will remain the source of static resource settings.
Runtime Python patch generation will move to Jinja templates.
The Kubernetes collection will apply rendered resource definitions.
Temporary Kustomize overlay directories will no longer be required.

Every Kubernetes service will keep a dedicated `10Ti` PV.
Every Kubernetes service dataset will keep an explicit ZFS quota.
New service datasets will use `tank/secure/backup/k0s/services/<service>` by default.
Explicitly ephemeral services may use `tank/secure/no-backup/k0s/services/<service>`.

## Secret handling

The following values are stored in the encrypted file.

- `private_cloud_secrets.storage.encryption_passphrase`
- `private_cloud_secrets.postgres.admin_password`
- `private_cloud_secrets.zabbix.database_password`
- `private_cloud_secrets.zabbix.admin_password`

The example file will contain placeholders only.
Python will request secrets with hidden input and confirmation.
Python will request and confirm the Vault password during configuration creation.
Python will write plaintext secrets only to a root-only temporary file under `/run`.
`ansible-vault` will create or replace `private-cloud.secrets.yml` from that file.
Python will delete the plaintext secrets file immediately after encryption.
The encrypted secrets file will remain for later reapplication.
The Vault password will not be stored persistently by the standard workflow.
The migration will not add credential-rotation behavior beyond the current installers.
Secret-bearing tasks will use `no_log: true`.
Secrets will not be registered into normal debug output.
Secrets will not be passed through process environment variables.
Kubernetes Secrets will be sent directly through the Kubernetes API.
The ZFS key file will be written atomically with mode `0600`.

Ansible Vault provides encryption at rest for the reusable secrets configuration.
It does not provide separate storage because the encrypted YAML file is the Vault data.
Root-only permissions reduce accidental exposure but do not protect secrets from a compromised root account.

## Idempotence and resume behavior

The Python checkpoint file will not be reproduced.
Ansible state checks will replace completed-stage bookkeeping.
Rerunning `sudo python3 ansible/install.py` will converge the host to the configured state.
An unchanged reapply will request only the Vault password and final confirmation.
Configuration update mode will prompt only for values selected for change.
Secret rotation mode will replace the chosen encrypted values.

- Resources created by the playbook will be reused on reapply.
- Pre-existing target resources will stop the initial installation.
- A managed pool will never be wiped or recreated on reapply.
- Existing datasets will receive declared mutable properties.
- Existing service quotas will not shrink below current usage.
- Unchanged templates will not restart services.
- Changed templates will notify handlers.
- Ready conditions will use bounded waits.

Stage flags will follow the declared dependency chain.
Tags will support operator-selected reruns without changing configuration.

## Python disposition

### Remove after role replacement

- `installer_helpers.py`
- `k0s_service_helpers.py`
- `python_setup/setup.py`
- `python_setup/setup_helpers.py`
- `k0s/install.py`
- `k0s/install_helpers.py`
- `k0s-services/postgres/install.py`
- `k0s-services/postgres/install_helpers.py`
- `k0s-services/zabbix/install.py`
- `k0s-services/zabbix/install_helpers.py`
- `k0s-services/zabbix/postgres_database.py`
- `k0s-services/zabbix/zabbix_api.py`
- `zabbix/install.py`
- `zabbix/install_helpers.py`
- `zfs/zfs-setup.py`
- `zfs/zfs_setup_helpers.py`
- `zfs/zfs_mount.py`

### Retain as runtime assets

- `ansible/install.py`
- `ansible/install_helpers.py`
- `zabbix/zabbix-zfs-collector.py`
- `zabbix/zabbix-memory-ecc-collector.py`

## Migration phases

### Phase 1: Ansible foundation

- Add the Ansible directory structure.
- Add the interactive Python entry point and prompt helpers.
- Add root, terminal, runtime-directory, and lock validation.
- Add hidden secret prompts and contextual hints.
- Add persistent public configuration management.
- Add temporary plaintext secret handling and cleanup.
- Add Ansible Vault creation, update, and password handling.
- Add the example configuration contract.
- Add the local single-host inventory.
- Add required Ansible collections.
- Add the preflight role.
- Add the sanitized configuration summary.

### Phase 2: Zabbix Agent

- Convert package installation.
- Convert asset installation.
- Convert agent configuration.
- Convert systemd management.
- Preserve runtime collector validation.

This phase has the smallest storage risk.

### Phase 3: Kubernetes services

- Convert PostgreSQL dataset management.
- Convert PostgreSQL resource deployment.
- Convert Zabbix database management.
- Convert Zabbix resource deployment.
- Convert Zabbix API management.
- Preserve fixed `10Ti` PV behavior.

### Phase 4: k0s

- Convert dataset hierarchy management.
- Convert quota management.
- Convert binary installation.
- Convert controller installation.
- Convert systemd dependency management.
- Convert node readiness checks.

### Phase 5: ZFS

- Convert disk discovery checks.
- Convert destructive authorization checks.
- Convert pool creation.
- Convert encryption setup.
- Convert dataset creation.
- Configure native OpenZFS systemd mount generation.
- Configure the ZFS list cache and ZED cache hook.
- Bind k0s to the generated ZFS mounts.
- Remove the Python mount helper and custom mount unit.
- Convert scrub services.

This phase runs last because it carries irreversible disk risk.

### Phase 6: Cutover

- Update all installation documentation.
- Make `sudo python3 ansible/install.py` the supported entry point.
- Remove the Python checkpoint workflow.
- Remove replaced installer Python files.
- Keep collector documentation with the retained assets.
- Confirm the Git tree contains no plaintext secret file.

## Completion criteria

- One interactive session requests every supported user input.
- One persistent public file supplies every non-secret desired-state variable.
- One persistent Vault file supplies every secret Ansible variable.
- The interactive session supplies fresh destructive authorization when required.
- Plaintext secret files are removed after encryption or a handled interruption.
- The playbook validates all values before host modification.
- The playbook runs without stage prompts.
- The playbook preserves the current storage layout.
- The pool applies every declared common ZFS property.
- General datasets inherit the declared common ZFS properties.
- The encrypted root has no quota or reservation.
- A missing ZFS key file is recovered from the validated vaulted passphrase.
- k0s uses the declared backup and no-backup dataset mapping.
- Every Kubernetes service owns a dedicated dataset.
- Every Kubernetes service dataset has a quota.
- Every leaf quota comes from the public configuration.
- Every Kubernetes service uses a fixed `10Ti` PV.
- PostgreSQL ZFS and server tuning matches the declared contract.
- Zabbix collects every metric declared in the monitoring contract.
- Zabbix applies every declared threshold and severity.
- Secrets do not appear in normal Ansible output.
- A successful playbook can be rerun without destructive changes.
- Existing incompatible infrastructure causes a clear failure.
- Native systemd key loading and ZFS mounting work without a custom unit.
- Missing OpenZFS systemd generator support causes installation failure.
- One supervised reboot proves the generated boot path.
- Reapply does not upgrade an installed OpenZFS package.
- Runtime ZFS, SMART, and ECC monitoring remains functional.
- The Zabbix Agent applies every declared managed setting.
- Stage-specific installer Python is removed after equivalent roles are complete.
