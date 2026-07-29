# Zabbix service

This installer deploys Zabbix Server 7.4.12 and its Nginx frontend.

## Prerequisites

- Install ZFS, k0s, and PostgreSQL first.
- PostgreSQL must create namespace `private-cloud`.
- PostgreSQL must create Service `postgres` on port 5432.
- PostgreSQL must create Secret `postgres-credentials`.
- Static Kubernetes resources are committed under `kustomize/base`.
- The installer creates a temporary permission-restricted Kustomize overlay.
- The PostgreSQL Secret is referenced and never recreated by this installer.

## Install

```bash
sudo python3 ./k0s-services/zabbix/install.py
```

The installer creates `tank/secure/k0s/services-backed/zabbix` by default.
It mounts that dataset at `/var/lib/zabbix` through a local PV and PVC.

The Zabbix Server NodePort is `31051` by default.
The web frontend NodePort is `30080` by default.

Override the ZFS quota or NodePorts when needed:

```bash
ZABBIX_STORAGE_SIZE=10G \
ZABBIX_SERVER_NODE_PORT=31051 \
ZABBIX_WEB_NODE_PORT=30080 \
sudo -E python3 ./k0s-services/zabbix/install.py
```

Point the host agent at `<node-address>:31051`.
Protect the web NodePort with a firewall or publish it through HTTPS and a VPN.
