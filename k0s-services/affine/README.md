# AFFiNE service

The AFFiNE service is managed by `ansible/roles/affine`.

- The Kustomize base is the authoritative Kubernetes workload definition.
- Render the public example with `python3 ansible/render_manifests.py affine --base k0s-services/affine/kustomize/base --values k0s-services/affine/site-values.example.yaml`.

- Configure `private_cloud.affine` in the public configuration.
- Store the internal database password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/affine`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV stores AFFiNE blobs and configuration.
- AFFiNE uses a dedicated database on the shared pgvector-enabled PostgreSQL service.
- AFFiNE uses the cluster-local Manticore service for full-text indexing.
- Schema version 1 updates ask whether to enable Manticore, disable AFFiNE, or cancel.
- Redis remains ephemeral and is rebuilt after restart.
- A versioned Job applies database migrations before the AFFiNE server rollout.
- The migration Job and server use the same Manticore indexer settings.
- The service listens inside the cluster on port `3010`.
- The configured NodePort publishes the service over HTTP.
- Forward the AFFiNE hostname to the configured NodePort through the TLS proxy.
- Preserve WebSockets in the TLS proxy.
- Database names and usernames are immutable after initialization.
- The AFFiNE role enables and verifies `vector` in its database.
