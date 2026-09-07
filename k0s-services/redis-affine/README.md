# Redis for AFFiNE service

The Redis cache for AFFiNE is managed by `ansible/roles/redis_affine`.

- Configure `private_cloud.redis_affine` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- Redis is reachable only inside the cluster on port `6379`.
- Redis data is ephemeral and is discarded when its Pod is replaced.
- No dataset, PV, PVC, or credentials are used.
