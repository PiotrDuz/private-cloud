# PostgreSQL service

This installer creates the PostgreSQL dataset and deploys one PostgreSQL pod.

- Export `POSTGRES_PASSWORD` and `POSTGRES_MAX_RAM` from the repository root.
- Run `sudo --preserve-env=POSTGRES_PASSWORD,POSTGRES_MAX_RAM python3 k0s-services/postgres/install.py`.
- Unset both values after the installation.
- `POSTGRES_DB` defaults to `zabbix`.
- `POSTGRES_USER` defaults to `zabbix`.
- `POSTGRES_MAX_RAM` is required and sets the pod memory limit.
- `POSTGRES_VOLUME_SIZE` defaults to `20G`.
- The image is `postgres:18.4-bookworm`.
- Static Kubernetes resources are committed under `kustomize/base`.
- The installer creates a temporary permission-restricted Kustomize overlay.
- The PostgreSQL Secret is applied through stdin and is never written to disk.

The installer references `postgres-credentials` from the static deployment.
It waits for the deployment and validates the dataset and Kubernetes resources.

Changing `POSTGRES_PASSWORD` after first initialization does not change the
existing database role password. Change the role password in PostgreSQL first.
