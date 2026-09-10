# Meilisearch service

The Meilisearch service is managed by `ansible/roles/meilisearch`.

- Configure `private_cloud.meilisearch` in the public configuration.
- Store the master key in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/meilisearch`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Emit JSON logs to stderr through `MEILI_EXPERIMENTAL_LOGS_MODE=json`.
