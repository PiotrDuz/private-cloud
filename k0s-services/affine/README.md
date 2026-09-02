# AFFiNE service

The AFFiNE service is managed by `ansible/roles/affine`.

- Configure `private_cloud.affine` in the public configuration.
- Store the internal database password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/affine`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores AFFiNE blobs and configuration.
- AFFiNE uses a dedicated database on the shared pgvector-enabled PostgreSQL service.
- Redis remains ephemeral and is rebuilt after restart.
- A versioned Job applies database migrations before the AFFiNE server rollout.
- The service listens inside the cluster on port `3010`.
- The configured NodePort publishes the service over HTTP.
- Forward the AFFiNE hostname to the configured NodePort through the TLS proxy.
- Preserve WebSockets in the TLS proxy.
- Database names and usernames are immutable after initialization.
- The AFFiNE role enables and verifies `vector` in its database.
