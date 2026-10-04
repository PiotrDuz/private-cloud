# AFFiNE service

The AFFiNE service is managed by `ansible/roles/affine`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Configure `private_cloud.affine` in the public configuration.
- Store the database password and OIDC client secret in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
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
- The Ingress preserves WebSocket connections.
- The AFFiNE role enables and verifies `vector` in its database.

## OpenCloud OIDC

- Configure native OIDC through the AFFiNE administration settings.
- Use the OpenCloud HTTPS URL as issuer with client ID `affine`.
- The role stores the client secret in `affine-credentials` as `OIDC_CLIENT_SECRET`.
- Register the HTTPS `/oauth/callback` redirect in OpenCloud.
- Use `sub`, `email`, and `name` claims with `openid profile email` scope.
- Set `claim_email_verified` to the absent `opencloud_admin_controlled_email` claim.
- Enable `oauth.providers.oidc.allowPrivateNetwork` for the trusted issuer origin.
- Keep workspace permissions and administrator grants within AFFiNE.
- Keep the self-hosted OIDC workspace within ten seats.

The pinned release's [OIDC claim mapping](https://github.com/toeverything/AFFiNE/blob/v0.27.3/packages/backend/server/src/plugins/oauth/providers/oidc.ts) accepts an absent verification claim and rejects an explicit false value. OpenCloud email identities must remain controlled by administrators.
