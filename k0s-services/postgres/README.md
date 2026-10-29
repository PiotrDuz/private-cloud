# PostgreSQL service

The PostgreSQL service is managed by `ansible/roles/postgres`.

- The installer reads `private_cloud.postgres` from the public configuration.
- The encrypted configuration holds the administrator password.
- The service dataset is `tank/secure/backup/k0s/services/postgres`.
- The dataset quota and reservation use the configured volume size.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The container memory limit uses the configured maximum RAM.
- PostgreSQL `shared_buffers` uses 25% of the configured maximum RAM.
- The image is the repository-pinned TensorChord PostgreSQL 18 build with pgvector and VectorChord.
- The PostgreSQL role initializes and verifies the `vector` extension.
- The PostgreSQL role initializes and verifies the `vchord` extension.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- PostgreSQL logs to stderr with an explicit timestamp and process prefix, without the file collector.
