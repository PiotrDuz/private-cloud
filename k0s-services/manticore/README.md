# Manticore service

The Manticore service is managed by `ansible/roles/manticore`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- The installer reads `private_cloud.manticore` from the public configuration.
- The service dataset is `tank/secure/backup/k0s/services/manticore`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster on HTTP port `9308`.
- AFFiNE uses Manticore as its full-text indexer.
