# Manticore service

The Manticore service is managed by `ansible/roles/manticore`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- Configure `private_cloud.manticore` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/manticore`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster on HTTP port `9308`.
- AFFiNE uses Manticore as its full-text indexer.
- Back up the dataset before changing the pinned Manticore image.
- Review Manticore release notes before upgrades.
