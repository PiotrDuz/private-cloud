# OpenCloud service

The OpenCloud service is managed by `ansible/roles/opencloud`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- The installer reads `private_cloud.opencloud` from the public configuration.
- The encrypted configuration holds the administrator password and the WOPI secret.
- The initial administrator password protects the built-in directory account, which signs in only through Stalwart.
- The service dataset is `tank/secure/backup/k0s/services/opencloud`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The separately provisioned `bleve-data` PVC stores the search index.
- The OpenCloud PV stores generated configuration, files, and web extensions.
- Apache Tika provides full-text content extraction.
- OnlyOffice uses the embedded OpenCloud collaboration service.
- The OpenCloud and OnlyOffice hostnames must resolve from the pods with trusted certificate chains.
- WOPI proof-key verification is enabled against the OnlyOffice discovery document.
- The app registry maps supported office formats to OnlyOffice.
- The official Draw.io extension embeds `https://embed.diagrams.net`.
- The first Draw.io installation requires outbound access to its pinned GitHub release.
- ConfigMap changes trigger a Deployment rollout through rendered checksums.
- The POSIX user storage driver requires the built-in NATS JetStream key-value cache for file IDs.
- A ClusterIP service exposes TCP `9200` only inside the cluster.
- Traefik publishes the configured hostname, including `/wopi` and `/collaboration`, through HTTPS.
- The collaboration service reads its WOPI signing secret only from the `opencloud-wopi` Secret.
- OnlyOffice never receives the WOPI secret, and OpenCloud never receives the OnlyOffice JWT secret.
- A WOPI secret rotation restarts OpenCloud through the Secret `resourceVersion` pod annotation.
- The image is the stable channel `opencloudeu/opencloud` pinned by tag and digest.
- The Draw.io installer image is pinned by tag and digest.

## Shared identity

- Stalwart is the OpenID Connect provider; OpenCloud's built-in provider does not run.
- `OC_OIDC_ISSUER` names the Stalwart issuer and the proxy rewrites discovery to it.
- The first sign-in of a Stalwart account creates its user in the built-in directory.
- The `email` claim matches the directory `mail` attribute, so an address maps to one user.
- The display name comes from `preferred_username`, because Stalwart omits `name` for accounts without a display name.
- New users receive the default user role.
- The installer sets the built-in administrator's address to the managed Stalwart mailbox account.
- That account therefore signs in as the OpenCloud administrator.
- The installer authenticates that change with a ten-minute app token from the `auth-app` service.
- The proxy validates opaque Stalwart access tokens through the userinfo endpoint.
- The content security policy allows OpenCloud Web to reach the Stalwart origin.
- Directory data stays on the OpenCloud dataset.
