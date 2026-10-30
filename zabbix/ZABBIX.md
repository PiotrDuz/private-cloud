# Zabbix Agent 2 and host monitoring

The host integration is managed by `ansible/roles/zabbix_agent`.

## Installation

- The `zabbix_agent` stage in the public configuration enables this integration.
- The Zabbix hostname is `monitor.<domain>`; set the active server through the constants in `ansible/service_catalog.yml`.
- The agent listens on localhost and uses unencrypted local transport.

## Runtime assets

- `zabbix-zfs-collector.py` collects pool, dataset, scrub, and snapshot metrics.
- `/etc/zabbix/private-cloud-datasets.json` lists enabled datasets to collect.
- `zabbix-memory-ecc-collector.py` collects Linux EDAC counters.
- `zabbix-kubernetes-collector.py` sums CPU, memory, and container restarts per Kubernetes workload.
- `zabbix-smartctl-wrapper` constrains privileged SMART commands.
- `collector_logging.py` sends ZFS, ECC, and SMART collector failures to the host journal.
- Alloy forwards collector diagnostics to OpenObserve without changing Zabbix metric output.
- Zabbix Agent uses system logging instead of a separate log file.
- Zabbix Agent and the host object authenticate with a PSK stored in the encrypted configuration.
- `zabbix-zfs-template.yaml` defines ZFS items, discovery, and alerts.
- `zabbix-memory-ecc-template.yaml` defines ECC items, discovery, and alerts.
- `zabbix-kubernetes-template.yaml` defines workload discovery, items, and restart alerts.
- `configure_dashboards.py` maintains the Private cloud dashboard from the host's live items.

## Dashboard

- Overview shows problems, CPU, memory, pool gauges, key status values, and host graphs.
- Storage shows pool throughput, operations, vdev state, scrub results, and ARC usage.
- Dataset capacity shows the enabled datasets by quota utilization and allocation.
- Disks shows SMART temperature, power-on hours, utilization, and I/O rates.
- Workloads shows memory, CPU cores, and container restarts per Kubernetes workload.
- Services shows certificate days left and Alloy retries and drops when the agent stage is enabled.

## SMART dependency

- ZFS and ECC triggers are bundled in this repository.
- SMART disk-health triggers come from the stock Zabbix template only.
- The Zabbix server stage requires `SMART by Zabbix agent 2 active` or its legacy name `SMART by Zabbix agent active 2`.
- The stock template supplies the disk failing, self-test, attribute threshold, and temperature triggers.
- Required Zabbix server version is 7.4; the pinned server and web images are 7.4.12.
- A missing SMART template fails the managed template assert during the Zabbix server stage.

## Version skew

- The host installs Zabbix Agent 2 from the 7.0 repository.
- The Zabbix server and web frontend run 7.4.12.
- The 7.4 server accepts the 7.0 agent; the agent supplies the ZFS, ECC, and SMART keys.

## Managed keys

- `zfs.metrics` reports pool health, errors, capacity, leaf quotas, and quota headroom.
- `zfs.snapshots` reports snapshot counts, retained bytes, and age.
- `memory.ecc.metrics` reports corrected and uncorrected ECC counters.
- `kubernetes.workloads` reports CPU, memory, and restarts per workload every five minutes.
- The native SMART plugin reports disk discovery and health.

## Kubernetes workloads

- The collector reads pods and the k0s metrics-server through two Kubernetes API calls per run.
- It authenticates with the `zabbix-agent` ServiceAccount token, which may only list pods and pod metrics.
- A workload is a Deployment, StatefulSet, or DaemonSet; Job pods are skipped because they are transient.
- CPU is in cores, memory is working-set bytes, and restarts count the containers of current pods.
- Restart counts reset when Kubernetes replaces a pod.
- A restart raises a Warning problem that resolves on the next unchanged sample.
- Discovered workloads that disappear are removed after seven days.

## Collector checks

- The collectors and agent keys can be run by hand; the commands are in the operations runbook.
- An empty SMART discovery result is expected when virtual hardware does not expose physical-drive SMART data.
