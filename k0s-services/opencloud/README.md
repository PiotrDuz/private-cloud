# OpenCloud service

The OpenCloud service is managed by `ansible/roles/opencloud`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Configure `private_cloud.opencloud` in the public configuration.
- Store the administrator password in the encrypted configuration.
- Change the initialized administrator password through OpenCloud UI or CLI.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/opencloud`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The separately provisioned `bleve-data` PVC stores the search index.
- The OpenCloud PV stores generated configuration, files, and web extensions.
- Apache Tika provides full-text content extraction.
- OnlyOffice uses the embedded OpenCloud collaboration service.
- The OpenCloud, OnlyOffice, and Keycloak hostnames must resolve from the pods with trusted certificate chains.
- WOPI proof checks are disabled for current OnlyOffice compatibility.
- The app registry maps supported office formats to OnlyOffice.
- The official Draw.io extension embeds `https://embed.diagrams.net`.
- The first Draw.io installation requires outbound access to its pinned GitHub release.
- ConfigMap changes trigger a Deployment rollout through rendered checksums.
- All supported cache stores use in-memory storage.
- A ClusterIP service exposes TCP `9200` only inside the cluster.
- Traefik publishes the configured hostname, including `/wopi` and `/collaboration`, through HTTPS.
- The collaboration service shares the OnlyOffice `JWT_SECRET` from `onlyoffice-credentials`.
- An OnlyOffice JWT secret rotation triggers an OpenCloud rollout through a rendered checksum.

## OIDC

- OpenCloud authenticates web, desktop, Android, and iOS clients through Keycloak.
- The issuer is `https://<keycloak-hostname>/realms/private-cloud`.
- Every client uses the public PKCE client `opencloud`.
- WebFinger publishes the `opencloud` client ID for web, desktop, Android, and iOS.
- The built-in `idp` service is excluded and the internal `idm` directory stays active.
- Autoprovisioning creates users in the internal directory on first sign-in.
- The `sub` claim maps to the OpenCloud `username` attribute for stable identities.
- Role assignment uses the OIDC `roles` claim and the default OpenCloud role mapping.
- The role values are `opencloudAdmin`, `opencloudSpaceAdmin`, `opencloudUser`, and `opencloudGuest`.

### Keycloak operator steps

- Create one public client `opencloud` in realm `private-cloud`.
- Enable the authorization code flow with PKCE.
- Add the redirect URIs for the OpenCloud web, desktop, Android, and iOS clients.
- Assign the `roles` client scope so realm roles appear in the `roles` claim.
- Provide the `sub`, `email`, `name`, `groups`, and `roles` claims.
- Map Keycloak realm roles to `opencloudAdmin`, `opencloudSpaceAdmin`, `opencloudUser`, or `opencloudGuest`.
- Set the backchannel logout URL to `https://<opencloud-hostname>/backchannel_logout`.
