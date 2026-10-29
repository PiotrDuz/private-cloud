# Redis for AFFiNE service

The Redis cache for AFFiNE is managed by `ansible/roles/redis_affine`.

- The installer reads `private_cloud.redis_affine.max_ram` from the public configuration.
- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- Redis is reachable only inside the cluster on port `6379`.
- Redis data is ephemeral and is discarded when its Pod is replaced.
- No dataset, PV, PVC, or credentials are used.
