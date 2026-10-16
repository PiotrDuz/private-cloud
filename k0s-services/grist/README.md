# Grist service

The Grist service is managed by `ansible/roles/grist`.

- Configure `private_cloud.grist` in the public configuration.
- Store the database password, session secret, boot key, and helper OIDC credentials in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/grist`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- PostgreSQL stores Grist metadata and the PV stores documents.
- Pyodide isolates user formulas without privileged container access.
- The service listens inside the cluster on port `8484`.
- A ClusterIP service exposes TCP `8484` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The route ConfigMap preserves WebSocket connections.
- Traefik authenticates every Grist request through the edge oauth2-proxy helper and OpenCloud.
- The helper redirects unauthenticated browsers to OpenCloud sign-in.
- Traefik strips client identity headers before authentication.
- Traefik routes `/oauth2/` on the Grist host to the helper without ForwardAuth.
- The helper returns the verified OpenCloud email as `X-Forwarded-User`.
- Grist trusts `X-Forwarded-User` on every request through `GRIST_IGNORE_SESSION`.
- Grist identity follows the helper cookie, which expires after eight hours.
- Grist access requires a browser session.
- Grist API keys do not work from outside the browser session.
- Logout calls `/oauth2/sign_out`, which ends the OpenCloud session and returns to OpenCloud.
- Use the boot key for initial administrator setup.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
