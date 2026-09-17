# Keycloak role

The Keycloak service is managed by `ansible/roles/keycloak`.

- Configure `private_cloud.keycloak` in the public configuration.
- Store the database password and administrator password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.

## Deployment

- The service dataset is `tank/secure/backup/k0s/services/keycloak`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity and are named `keycloak-data`.
- PostgreSQL stores the realm, identity, and client configuration in the `keycloak` database.
- The database login role is `keycloak`.
- The realm import JSON is rendered into the `keycloak-realm` Secret and mounted at `/opt/keycloak/data/import`.
- Keycloak starts with `--import-realm`.
- Keycloak skips the import when the realm already exists.
- Realm configuration is immutable through this installer; recreate the realm to apply changes.
- The service listens inside the cluster on port `8080`.
- The management and health endpoints listen inside the cluster on port `9000`.
- A ClusterIP service exposes TCP `8080` only inside the cluster.
- Traefik publishes `https://<keycloak.hostname>` through HTTPS with the cloudflare certresolver.
- The NetworkPolicy admits ingress from the edge Traefik pods only.
- The NetworkPolicy admits egress to PostgreSQL, cluster DNS, and the Traefik internal IP for backchannel logout.

## Realm contract

- The realm name and issuer are fixed to `private-cloud` and `https://<keycloak.hostname>/realms/private-cloud`.
- The issuer uses `KC_HOSTNAME`, `KC_HTTP_ENABLED`, and `KC_PROXY_HEADERS=xforwarded` for Traefik TLS termination.
- The administrator user is `private_cloud.keycloak.admin_username` with the `realm-management` `realm-admin` client role.
- The administration console is at `https://<keycloak.hostname>/admin/private-cloud/console/`.
- The Stalwart WebUI callbacks use `private_cloud.stalwart.hostname`, not the mail domain.
- Public clients require authorization code flow with PKCE `S256`.
- Confidential clients authenticate with a client secret.
- Clients are created only for enabled application stages.

## OIDC clients

| Client ID | Type | Redirect URIs |
| --- | --- | --- |
| `opencloud` | Public PKCE | `https://<opencloud.hostname>/`, `https://<opencloud.hostname>/oidc-callback.html`, `https://<opencloud.hostname>/oidc-silent-redirect.html`, `http://127.0.0.1`, `http://localhost`, `oc://android.opencloud.eu`, `oc://ios.opencloud.eu` |
| `stalwart` | Public PKCE | `https://<stalwart.hostname>/admin/oauth/callback`, `https://<stalwart.hostname>/account/oauth/callback` |
| `stalwart-webui` | Public PKCE | `https://<stalwart.hostname>/admin/oauth/callback`, `https://<stalwart.hostname>/account/oauth/callback` |
| `grist-forward-auth` | Confidential | `https://<grist.hostname>/_oauth` |
| `affine` | Confidential | `https://<affine.hostname>/oauth/callback` |
| `immich` | Confidential | `https://<immich.hostname>/auth/login`, `https://<immich.hostname>/user-settings`, `app.immich:///oauth-callback` |
| `jellyfin` | Confidential | `https://<media.hostname>/sso/OIDC/Callback/keycloak` |

- `stalwart-webui` exists because the upstream Stalwart WebUI hardcodes that public client id.
- The `stalwart` and `stalwart-webui` clients include an audience mapper that adds `stalwart` to access tokens.
- The `opencloud` client includes a realm-role mapper that emits the `roles` claim used by `PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM`.
- OpenCloud registers a backchannel logout URL at `https://<opencloud.hostname>/backchannel_logout`.
- OpenCloud requires `WEBFINGER_*_OIDC_CLIENT_ID=opencloud` for web, desktop, Android, and iOS.
- Immich registers a backchannel logout URL at `https://<immich.hostname>/api/oauth/backchannel-logout`.
- The Jellyfin provider id in the callback path defaults to `keycloak`.

## Upstream sources

- OpenCloud clients: <https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp/>
- Stalwart OIDC directory: <https://stalw.art/docs/auth/backend/oidc/>
- Stalwart WebUI client id and callbacks: <https://stalw.art/docs/auth/oauth/client-registration/>
- Grist forward authentication: <https://support.getgrist.com/install/forwarded-headers/>
- AFFiNE OIDC: <https://affine.pro/enterprise>
- Immich OAuth: <https://docs.immich.app/administration/oauth/>
- Jellyfin plugin: <https://github.com/aussierk/jellyfin-plugin-oidc>
- Keycloak hostname: <https://www.keycloak.org/server/hostname>
- Keycloak health checks: <https://www.keycloak.org/observability/health>

## Live verification

- Confirm Traefik forwards the `X-Forwarded-*` headers for the configured hostname.
- Confirm the Stalwart WebUI and the OpenCloud native clients accept the issuer.
- Confirm the Jellyfin plugin provider id matches `keycloak`.
