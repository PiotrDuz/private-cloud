# AFFiNE service

The AFFiNE service is managed by `ansible/roles/affine`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Configure `private_cloud.affine` in the public configuration.
- Store the internal database password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/affine`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores AFFiNE blobs and configuration.
- AFFiNE uses a dedicated database on the shared pgvector-enabled PostgreSQL service.
- AFFiNE uses the cluster-local Manticore service for full-text indexing.
- Redis remains ephemeral and is rebuilt after restart.
- A database preparation Job initializes the fresh AFFiNE schema before the server starts.
- The preparation Job and server use the same Manticore indexer settings.
- The service listens inside the cluster on port `3010`.
- Fixed NodePort `30310` publishes the service over HTTP.
- Forward the AFFiNE hostname to NodePort `30310` through the TLS proxy.
- Preserve WebSockets in the TLS proxy.
- The AFFiNE role enables and verifies `vector` in its database.
