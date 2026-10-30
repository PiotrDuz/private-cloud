# Grist service

The Grist service is managed by `ansible/roles/grist`.

- The installer reads `private_cloud.grist` from the public configuration.
- The encrypted configuration holds the database password, session secret, boot key, and helper OIDC credentials.
- The service dataset is `tank/secure/backup/k0s/services/grist`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- PostgreSQL stores Grist metadata and the PV stores documents.
- Pyodide isolates user formulas without privileged container access.
- The service listens inside the cluster on port `8484`.
- A ClusterIP service exposes TCP `8484` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The route ConfigMap preserves WebSocket connections.
- Traefik authenticates every Grist request through the edge oauth2-proxy helper and Stalwart.
- The helper redirects unauthenticated browsers to Stalwart sign-in.
- Traefik strips client identity headers before authentication.
- Traefik routes `/oauth2/` on the Grist host to the helper without ForwardAuth.
- The helper returns the Stalwart account email as `X-Forwarded-User`.
- Grist trusts `X-Forwarded-User` on every request through `GRIST_IGNORE_SESSION`.
- Grist identity follows the helper cookie, which expires after eight hours.
- Grist access requires a browser session.
- Grist API keys do not work from outside the browser session.
- Logout calls `/oauth2/sign_out`, which clears the helper cookie and returns to Stalwart sign-in.
- `GRIST_DEFAULT_EMAIL` makes the managed Stalwart mailbox account the Grist administrator.
- The boot key unlocks the initial administrator setup page.
- `GRIST_IN_SERVICE` keeps the server in service, so the setup gate never blocks Stalwart accounts.
- Only team site members open documents; other accounts see Access denied.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
