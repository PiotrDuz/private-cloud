# Private cloud installation

The supported installer collects the full configuration and runs one unattended Ansible playbook.

## Prerequisites

- Use Ubuntu for all stages or Debian with the Zabbix Agent stage disabled.
- Use OpenZFS userland and kernel modules version 2.3 or newer.
- Install Python 3, PyYAML, Ansible, and the Python Kubernetes client.
- Install the collections from `ansible/requirements.yml`.
- Run the installer from an interactive root terminal.

The ZFS role enforces the OpenZFS 2.3 minimum before it changes storage because the PostgreSQL dataset uses the [`prefetch` property](https://openzfs.github.io/openzfs-docs/man/v2.3/7/zfsprops.7.html).

```bash
sudo ansible-galaxy collection install -r ansible/requirements.yml
sudo python3 ansible/install.py
```

## Configuration

- `ansible/config/private-cloud.yml` stores non-secret desired state.
- `ansible/config/private-cloud.secrets.yml` stores Ansible Vault ciphertext.
- `ansible/config/private-cloud.example.yml` documents the configuration contract.
- The Vault password is never stored by the installer.
- The `CREATE tank` authorization is requested only before new pool creation.

## Lifecycle

- Create collects and validates the complete configuration.
- Update changes selected public or secret values.
- Reapply converges the existing configuration.
- Rotate replaces selected encrypted values.
- Ansible runs all enabled stages in dependency order.
- The k0s stage creates the shared `private-cloud` Kubernetes namespace.

## Reboot verification

- Reboot the host under supervision after the first successful installation.
- Reapply the configuration after reboot to verify native ZFS mounts and k0s ordering.
- Do not use the installer for unattended operating-system or OpenZFS upgrades.

## Operations

- Read [the operations contract](docs/OPERATIONS.md) before storing irreplaceable data.
- Record the site-specific values in [the operator record](docs/OPERATOR_RECORD.md).
- Treat backup, public networking, and external monitoring as operator work until automation implements them.
- Use [the recovery runbook](docs/RECOVERY.md) for disk or host failure and upgrade rollback.
- Follow [the contribution guide](CONTRIBUTING.md) for repository changes.
