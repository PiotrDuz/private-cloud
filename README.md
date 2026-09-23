# Private cloud installation

The supported installer collects the full configuration and runs one unattended Ansible playbook.

## Prerequisites

- Use Ubuntu for all stages or Debian with the Zabbix Agent stage disabled.
- Use OpenZFS userland and kernel modules version 2.3 or newer.
- Install Python 3, PyYAML, Ansible, and the Python Kubernetes client.
- Install the collections from `ansible/requirements.yml`.
- Run the installer from an interactive root terminal.
- Enable the Intel integrated GPU in firmware for the default Immich OpenVINO acceleration.

The ZFS role enforces the OpenZFS 2.3 minimum before it changes storage because the PostgreSQL dataset uses the [`prefetch` property](https://openzfs.github.io/openzfs-docs/man/v2.3/7/zfsprops.7.html).

```bash
sudo ansible-galaxy collection install -r ansible/requirements.yml
sudo python3 ansible/install.py
```

## Configuration

- `ansible/config/private-cloud.yml` stores non-secret desired state.
- `ansible/config/private-cloud.secrets.yml` stores Ansible Vault ciphertext.
- `ansible/config/private-cloud.example.yml` documents the configuration contract at public schema version 8 and secrets schema version 4.
- Public hostnames are configured per service, including the Keycloak hostname `auth.example.com`.
- The Cloudflare managed records cover every published hostname.
- The Vault password is never stored by the installer.
- The `CREATE tank` authorization is requested only before new pool creation.
- The installer reads the multiline OpenVPN profile from a file path.

## Kubernetes manifests

- `k0s-services/<service>/templates/*.yaml.j2` contains each service definition.
- The owning Ansible role renders and applies those templates directly.
- User-configurable values are in the public and encrypted configuration files.
- Application web services use ClusterIP behind Traefik.
- Zabbix server TCP `31051` is the only application NodePort.
- The k0s release pin is in `ansible/roles/k0s/defaults/main.yml`.
- Zabbix host settings are in `ansible/service_catalog.yml`.
- The logging stage deploys Alloy and OpenObserve in `observability`.
- The notifications stage enables OpenObserve SMTP and Zabbix email actions.
- Keycloak is the shared OIDC provider for the enabled user-facing services.
- The edge forward-auth helper authenticates Grist through Keycloak.
- The media stage keeps the ARR stack and shared media library on `no-backup` datasets.
- Keycloak, Redis for AFFiNE, Intel GPU support, and Immich are independent installer stages.
- Immich uses the shared PostgreSQL service with pgvector and VectorChord.
- The project is greenfield and has no configuration migrations or compatibility paths.

## Lifecycle

- Create collects and validates the complete configuration.
- Update changes selected public or secret values.
- Reapply converges the existing configuration.
- Rotate replaces selected encrypted values.
- Validate runs the separate live checks after operator setup.
- Ansible runs all enabled stages in dependency order.
- The k0s stage creates the workload and infrastructure namespaces.

## Reboot verification

- Reboot the host under supervision after the first successful installation.
- Reapply the configuration after reboot to verify native ZFS mounts and k0s ordering.
- Select `validate` in the installer to check the installed system and alert delivery.
- Do not use the installer for unattended operating-system or OpenZFS upgrades.

## Operations

- Use [the operations runbook](docs/OPERATIONS.md) for monitoring and incident investigation.
- Treat backups, router/NAT configuration, external monitoring, and live acceptance as operator work tracked in [the operator setup runbook](docs/SETUP.md).
- Read [the networking architecture and boundaries](docs/NETWORKING.md) for the implemented VPN, ingress, firewall, identity, and media isolation design.

Kubernetes workloads keep CPU requests without CPU limits; remove the former Immich `max_cpu`, `machine_learning_max_cpu`, and `valkey_max_cpu` settings from public configuration.

The media stage requires `private_cloud_secrets.media.qbittorrent_password` in Vault for automatic ARR connections. The Keycloak stage requires its database and administrator passwords; OIDC client secrets for Grist, AFFiNE, Immich, and Jellyfin are not rotatable through the installer.
