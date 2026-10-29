# AFFiNE service

The AFFiNE service is managed by `ansible/roles/affine`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- The installer reads `private_cloud.affine` from the public configuration.
- The encrypted configuration holds the database password and OIDC client secret.
- The service dataset is `tank/secure/backup/k0s/services/affine`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores AFFiNE blobs and configuration.
- AFFiNE runs as UID 0 inside a user namespace mapped to an unprivileged host UID.
- AFFiNE uses a dedicated database on the shared pgvector-enabled PostgreSQL service.
- AFFiNE uses the cluster-local Manticore service for full-text indexing.
- AFFiNE uses the independently managed `redis-affine` cache service.
- A database preparation Job initializes the fresh AFFiNE schema before the server starts.
- The preparation Job and server use the same Manticore indexer settings.
- The service listens inside the cluster on port `3010`.
- A ClusterIP service exposes TCP `3010` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- Visitors land on the sign-in page because the guest demo workspace is disabled.
- `AFFINE_SERVER_EXTERNAL_URL` sets the public `https://<hostname>` origin for generated links and OAuth redirects.
- The route ConfigMap preserves WebSocket connections.
- The installer creates the first administrator as the managed Stalwart mailbox account before applying the route ConfigMap.
- The installer skips the claim when AFFiNE reports `initialized`.
- The administrator password must contain 16 to 32 characters.
- The server and the preparation Job drop all capabilities and disable privilege escalation.
- AFFiNE needs no capabilities because it runs as the owner of its data and binds port `3010`.
- The role alters the PostgreSQL role password when the stored database password changes.
- The pod annotation carries the credentials Secret revision to restart the pod on rotation.
- The AFFiNE role enables and verifies `vector` in its database.

## Stalwart OIDC

- The role renders `config.json` into the `affine-credentials` Secret and mounts it at `/app/config.json`.
- The file disables the guest demo workspace and configures the OIDC provider.
- The provider uses the Stalwart issuer with the confidential client `affine`.
- Stalwart allows only the `https://<affine hostname>/oauth/callback` redirect.
- Claims map `sub`, `email`, and `name` with the `openid email profile` scope.
- `allowPrivateNetwork` lets the server reach the issuer, which LAN DNS resolves to a private address.
- The first sign-in of a Stalwart account creates its AFFiNE user.
- The first administrator is the managed Stalwart mailbox account, so its sign-in links to the claimed account.
- Workspace permissions and administrator grants stay within AFFiNE.
- The self-hosted workspace allows ten seats.
