# Zabbix service

The Zabbix server and web frontend are managed by `ansible/roles/zabbix_server`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- The installer reads `private_cloud.zabbix` from the public configuration.
- The encrypted configuration holds database and administrator passwords and the agent PSK.
- The service dataset is `tank/secure/backup/k0s/services/zabbix`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- Zabbix Server uses fixed NodePort `31051`.
- The web frontend uses ClusterIP behind Traefik HTTPS.
- The monitored host name is fixed as `private-cloud-zabbix`.
- The host agent connects to `127.0.0.1:31051`.
- The agent and the Zabbix host object use a PSK from the encrypted configuration.
- The PSK identity is `private_cloud_zabbix_psk_identity` in the service catalog.
- A PSK rotation updates the host object and restarts the agent.
- The installer publishes the web route ConfigMap only after it sets the administrator password.
- The role imports the ZFS and memory ECC templates.
- The role links the active Linux, SMART, ZFS, and ECC templates.
- The host firewall limits NodePort `31051` to configured local networks.
- The service catalog creates dataset warnings at 80% and high alerts at 90%.
- Zabbix independently probes HTTPS and SMTP STARTTLS endpoints, plus Alloy when logging is enabled.
- Alert emails go directly to Stalwart's internal service on TCP `2525` without SMTP credentials or TLS.
- Zabbix reports Alloy health, metrics availability, retries, and dropped entries.
- The health collector runs without sudo or OpenObserve administrator credentials.
- Zabbix Agent uses system logging collected from the host journal by Alloy.
- ZFS, ECC, and SMART collector failures reach OpenObserve while metric output stays with Zabbix.
- Shared dataset and edge certificate checks still cover OpenObserve storage and its HTTPS hostname.
- The notifications stage configures the administrator media and Warning-or-higher email action.
- Problems send recovery messages and daily reminders to the Stalwart forwarding alias.
- Live recipient delivery remains an operator acceptance check.
