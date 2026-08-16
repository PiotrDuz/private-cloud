# Zabbix service

This installer deploys Zabbix Server 7.4.12 and its Nginx frontend.

## Prerequisites

- Install ZFS, k0s, and PostgreSQL first.
- PostgreSQL must create namespace `private-cloud`.
- PostgreSQL must run deployment and Service `postgres`.
- The PostgreSQL administrator database and role must both be `postgres`.
- Static Kubernetes resources are committed under `kustomize/base`.
- Do not apply `kustomize/base` directly because the installer supplies validated runtime values.
- The installer creates a temporary permission-restricted Kustomize overlay.
- The installer owns the Zabbix database, login role, and credentials Secret.

## Install

The interactive setup prompts for the Zabbix administrator credentials:

```bash
sudo python3 ./python_setup/setup.py
```

For a standalone installation, pass the database and frontend passwords securely:

```bash
read -rsp "Zabbix database password: " ZABBIX_DB_PASSWORD
echo
read -rsp "Zabbix administrator password: " ZABBIX_ADMIN_PASSWORD
echo
export ZABBIX_DB_PASSWORD ZABBIX_ADMIN_PASSWORD
sudo --preserve-env=ZABBIX_DB_PASSWORD,ZABBIX_ADMIN_PASSWORD python3 ./k0s-services/zabbix/install.py
unset ZABBIX_DB_PASSWORD ZABBIX_ADMIN_PASSWORD
```

The installer creates `tank/secure/k0s/services-backed/zabbix` by default.
Reruns reject a requested size below the existing ZFS, PV, or PVC capacity.
It mounts that dataset at `/var/lib/zabbix` through a local PV and PVC.

The Zabbix Server NodePort is `31051` by default.
The web frontend NodePort is `30080` by default.

Override the database identifiers, ZFS quota, NodePorts, or administrator user when needed:

```bash
sudo --preserve-env=ZABBIX_DB_PASSWORD,ZABBIX_ADMIN_PASSWORD env \
  ZABBIX_DB_NAME=zabbix \
  ZABBIX_DB_USER=zabbix \
  ZABBIX_STORAGE_SIZE=10G \
  ZABBIX_SERVER_NODE_PORT=31051 \
  ZABBIX_WEB_NODE_PORT=30080 \
  ZABBIX_ADMIN_USERNAME=Admin \
  python3 ./k0s-services/zabbix/install.py
```

The monitored host name is fixed to `private-cloud-zabbix`.

The installer creates or updates the Zabbix PostgreSQL login role.
It creates the Zabbix database and applies `zabbix-postgres-credentials`.

The installer uses the local frontend API after deployment.
It replaces the initial `Admin`/`zabbix` login with the requested administrator credentials.
Reruns use the requested credentials and tolerate Zabbix temporary login blocks.
It imports the ZFS and memory ECC templates.
It creates or updates the host in the `Private cloud` group.
It links the Linux, SMART, ZFS, and memory ECC active templates.
It creates or updates the `Private cloud ZFS storage` dashboard.
It configures host connections as unencrypted.

Point the host agent at `127.0.0.1:31051` on the same machine.
Protect the web NodePort with a firewall or publish it through HTTPS and a VPN.
