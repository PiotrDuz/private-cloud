# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## Monitoring

- [ ] Configure external outage monitoring independent of this host and Stalwart.

## Services

- [ ] Select Prowlarr indexers and provide their credentials.
- [ ] Reach the unpublished Prowlarr UI through `sudo k0s kubectl port-forward -n media service/prowlarr 9696:9696`.
- [ ] Select the `private-cloud` profile when adding Sonarr series, Radarr movies, or import lists.

## Identity

- [ ] Sign in to the Keycloak administration console at `https://<keycloak-hostname>/admin/private-cloud/console/` with the configured administrator.
- [ ] Create user accounts and assign the roles each application expects.
- [ ] Keep a local password administrator in each OIDC-enabled application as a break-glass account.
- [ ] Recreate the realm through the installer when a client secret or client configuration changes.

### AFFiNE OIDC

- [ ] In the AFFiNE administration panel, add a generic OAuth2/OIDC provider.
- [ ] Set the issuer URL to `https://<keycloak-hostname>/realms/private-cloud`.
- [ ] Set the client id to `affine` and the secret to `private_cloud_secrets.affine.oidc_client_secret`.
- [ ] Allow the redirect URI `https://<affine-hostname>/oauth/callback`.
- [ ] Note the ten-seat limit for the self-hosted AFFiNE workspace.

### Jellyfin OIDC

- [ ] Confirm the confidential client `jellyfin` allows `https://<jellyfin-hostname>/sso/OIDC/Callback/keycloak`.
- [ ] Create and assign the realm roles `jellyfin-admins` and `jellyfin-users`.
- [ ] Run **Test Connection** in the plugin admin page to verify and pin the Keycloak discovery endpoints.
- [ ] Authorize native clients through `https://<jellyfin-hostname>/sso/OIDC/QuickConnect/keycloak`.

## Network and DNS

- [ ] Configure router forwarding for TCP 25, TCP 443, and the AmneziaWG UDP port.
- [ ] Configure LAN and VPN split DNS.
- [ ] Resolve the Keycloak hostname to the Traefik address for LAN clients and pods.
- [ ] Request the PTR record for the mail design from the ISP.
- [ ] Send a message through the external inbox and confirm the forward reaches the Stalwart inbox.

## Deployment acceptance

- [ ] Complete the deployment acceptance checklist in [NETWORKING.md](NETWORKING.md#deployment-acceptance).
- [ ] Confirm the router, DNS, certificates, and media integrations in the live environment.
