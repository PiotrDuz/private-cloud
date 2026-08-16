# PostgreSQL service

This installer creates the PostgreSQL dataset and deploys one PostgreSQL pod.

- Export `POSTGRES_ADMIN_PASSWORD` and `POSTGRES_MAX_RAM` from the repository root.
- Run `sudo --preserve-env=POSTGRES_ADMIN_PASSWORD,POSTGRES_MAX_RAM python3 k0s-services/postgres/install.py`.
- Unset both values after the installation.
- The administrator database and role are both `postgres`.
- `POSTGRES_MAX_RAM` is required and sets the pod memory limit.
- `POSTGRES_VOLUME_SIZE` defaults to `20G`.
- The image is `postgres:18.4-bookworm`.
- Static Kubernetes resources are committed under `kustomize/base`.
- Do not apply `kustomize/base` directly because the installer supplies validated runtime values.
- The installer creates a temporary permission-restricted Kustomize overlay.
- The administrator Secret is applied through stdin and is never written to disk.

The installer creates `postgres-admin-credentials` for the PostgreSQL pod.
It does not create application databases or roles.
Each application installer owns its database, role, and credentials Secret.

Changing `POSTGRES_ADMIN_PASSWORD` after initialization does not change the
existing administrator role password. Change the role password first.
