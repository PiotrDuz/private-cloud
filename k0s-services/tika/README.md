# Apache Tika service

The Apache Tika service is managed by `ansible/roles/tika`.

- The installer reads `private_cloud.tika` from the public configuration.
- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- The service dataset is `tank/secure/backup/k0s/services/tika`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster on port `9998`.
- The persistent volume is mounted at `/var/lib/tika`.
- Tika is stateless and the PV follows the repository service-storage policy.
