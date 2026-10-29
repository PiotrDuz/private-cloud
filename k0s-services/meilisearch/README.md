# Meilisearch service

The Meilisearch service is managed by `ansible/roles/meilisearch`.

- The installer reads `private_cloud.meilisearch` from the public configuration.
- The encrypted configuration holds the master key.
- Only administration uses the master key.
- The Stalwart role creates a scoped `st_*` search key for Stalwart.
- The service dataset is `tank/secure/backup/k0s/services/meilisearch`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Meilisearch emits JSON logs to stderr through `MEILI_EXPERIMENTAL_LOGS_MODE=json`.
