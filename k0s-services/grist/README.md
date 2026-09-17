# Grist service

The Grist service is managed by `ansible/roles/grist`.

- Configure `private_cloud.grist` in the public configuration.
- Store the database password, session secret, and boot key in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/grist`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- PostgreSQL stores Grist metadata and the PV stores documents.
- Pyodide isolates user formulas without privileged container access.
- The service listens inside the cluster on port `8484`.
- A ClusterIP service exposes TCP `8484` only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The Ingress preserves WebSocket connections.
- Traefik authenticates Grist through the edge ForwardAuth helper and Keycloak.
- Traefik strips client identity headers before authentication.
- Grist trusts `X-Forwarded-User` for the single team site.
- The logout path clears the helper cookie and returns to `/signed-out`.
- Use the boot key for initial administrator setup.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
