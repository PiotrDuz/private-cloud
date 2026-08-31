# Zabbix Agent 2 and host monitoring

The host integration is managed by `ansible/roles/zabbix_agent`.

## Installation

- Enable `private_cloud.stages.zabbix_agent` in the public configuration.
- Set the monitored hostname and active server under `private_cloud.zabbix`.
- Run `sudo python3 ansible/install.py` from the repository root.
- The agent listens on localhost and uses unencrypted local transport.

## Runtime assets

- `zabbix-zfs-collector.py` collects pool, dataset, scrub, and snapshot metrics.
- `zabbix-memory-ecc-collector.py` collects Linux EDAC counters.
- `zabbix-smartctl-wrapper` constrains privileged SMART commands.
- `zabbix-zfs-template.yaml` defines ZFS items, discovery, and alerts.
- `zabbix-memory-ecc-template.yaml` defines ECC items, discovery, and alerts.

## Managed keys

- `zfs.metrics` reports pool health, errors, capacity, and leaf quotas.
- `zfs.snapshots` reports snapshot counts, retained bytes, and age.
- `memory.ecc.metrics` reports corrected and uncorrected ECC counters.
- The native SMART plugin reports disk discovery and health.

## Local verification

```bash
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py metrics | python3 -m json.tool
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py snapshots | python3 -m json.tool
sudo -u zabbix /usr/local/libexec/zabbix/memory-ecc-collector.py | python3 -m json.tool
sudo zabbix_agent2 -t zfs.metrics
sudo zabbix_agent2 -t zfs.snapshots
sudo zabbix_agent2 -t memory.ecc.metrics
sudo zabbix_agent2 -t smart.disk.discovery
```

An empty SMART discovery result is expected when virtual hardware does not expose physical-drive SMART data.
