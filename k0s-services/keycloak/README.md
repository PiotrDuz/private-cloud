# Keycloak service

The Keycloak service is managed by `ansible/roles/keycloak`.

- Configure `private_cloud.keycloak` in the public configuration.
- Store the database password and administrator password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/keycloak`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- PostgreSQL stores the realm, identity, and client configuration in the `keycloak` database.
- The realm import JSON is mounted from the `keycloak-realm` Secret.
- The realm import runs on startup and is skipped when the realm exists.
- A ClusterIP service exposes TCP `8080` only inside the cluster.
- The management and health endpoints listen on TCP `9000` inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

## OIDC

- Keycloak is the shared OIDC provider for the realm `private-cloud`.
- The issuer is `https://<keycloak-hostname>/realms/private-cloud`.
- OpenCloud authenticates through the public PKCE client `opencloud`.
- Stalwart authenticates through the public PKCE clients `stalwart` and `stalwart-webui`.
- Grist forward authentication uses the confidential client `grist-forward-auth`.
- AFFiNE uses the confidential client `affine`.
- Immich uses the confidential client `immich` with backchannel logout.
- Jellyfin uses the confidential client `jellyfin`.
- The exact client redirect matrix is documented in `ansible/roles/keycloak/README.md`.
