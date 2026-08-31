# Zabbix service

The Zabbix server and web frontend are managed by `ansible/roles/zabbix_server`.

- Configure `private_cloud.zabbix` in the public configuration.
- Store database and administrator passwords in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/zabbix`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- Zabbix Server uses the configured server NodePort.
- The web frontend uses the configured web NodePort.
- The role imports the ZFS and memory ECC templates.
- The role links the active Linux, SMART, ZFS, and ECC templates.
- Publish the frontend through HTTPS and a protected network.
