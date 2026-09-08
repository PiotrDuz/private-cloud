# Zabbix service

The Zabbix server and web frontend are managed by `ansible/roles/zabbix_server`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Configure `private_cloud.zabbix` in the public configuration.
- Store database and administrator passwords in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/zabbix`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- Zabbix Server uses fixed NodePort `31051`.
- The web frontend uses ClusterIP behind Traefik HTTPS.
- The monitored host name is fixed as `private-cloud-zabbix`.
- The host agent connects to `127.0.0.1:31051`.
- The role imports the ZFS and memory ECC templates.
- The role links the active Linux, SMART, ZFS, and ECC templates.
- The host firewall limits NodePort `31051` to configured local networks.
