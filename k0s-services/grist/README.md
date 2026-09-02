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
- The configured NodePort publishes the service over HTTP.
- Forward the Grist hostname to the configured NodePort through the TLS proxy.
- Preserve WebSockets in the TLS proxy.
- Use the boot key for initial administrator setup.
