# Zabbix Agent 2 and OpenZFS monitoring

This directory contains a host-side Zabbix Agent 2 installer, the native SMART
plugin setup, read-only OpenZFS collectors, and a read-only Linux EDAC memory
ECC collector. It targets Ubuntu 26.04 and Zabbix Agent 2 7.0 LTS.

## Architecture

Run `zabbix-agent2` as a system service on the ZFS host. Run Zabbix Server
7.4.12, PostgreSQL, and the web frontend in Kubernetes on the same machine.
The agent uses unencrypted active checks through the local Zabbix Server
NodePort. It listens only on `127.0.0.1` for passive checks.

ZED and the monthly scrub timer remain separate. Zabbix observes their results;
it does not replace local ZFS event processing or initiate scheduled scrubs.
The Agent 2 SMART plugin uses `smartmontools` to monitor physical drives when
the storage controller exposes SMART data to the operating system.

## Install

Run the interactive setup from the repository root:

```bash
sudo python3 ./python_setup/setup.py
```

The Zabbix service stage prompts for the PostgreSQL role, database password,
frontend administrator credentials. It creates the database,
imports the custom templates, creates or updates the host, and
links the Linux, SMART, ZFS, and memory ECC active templates. It also creates
the `Private cloud ZFS storage` dashboard. The host-agent
stage uses the fixed `private-cloud-zabbix` host name and defaults to `127.0.0.1:31051`.

For a standalone agent installation:

```bash
sudo python3 ./zabbix/install.py \
  --server-active 127.0.0.1:31051
```

The monitoring transport is plaintext because the agent and server run on the
same machine. Rerunning the installer removes old managed TLS settings and
keeps the agent in unencrypted mode.

The installer creates a backup of the package configuration at
`/etc/zabbix/zabbix_agent2.conf.pre-private-cloud` before its first change.

Zabbix Server is reachable at `<node-address>:31051`.
The frontend is reachable at `http://<node-address>:30080`.
Publish the frontend through HTTPS and preferably a VPN.

## SMART monitoring

The Python installer adds `smartmontools`, configures the built-in Agent 2 SMART
plugin, and installs `/etc/sudoers.d/zabbix-smartctl`. The sudo rule permits
only the read and discovery command forms used by the plugin. It is
syntax-checked with `visudo` before installation.

The plugin calls the root-owned
`/usr/local/libexec/zabbix/smartctl-wrapper`. It runs
`/usr/sbin/smartctl` and preserves invocation, device-access, SMART-command,
and signal failures. It normalizes only smartctl's device-health exit bits,
because Zabbix issue ZBX-27105 causes affected Agent 2 versions to reject the
JSON instead of discovering an unhealthy disk. The health findings remain in
the JSON for the official template to evaluate.

The SMART plugin provides these native keys:

- `smart.disk.discovery`
- `smart.disk.get`
- `smart.attribute.discovery`

The official `SMART by Zabbix agent active 2` template discovers supported
HDD, SSD, and NVMe devices and creates the health, temperature, lifetime, and
attribute items and triggers.

This host currently uses VMware virtual SCSI disks. A guest may receive an
empty discovery result because VMware normally does not pass physical-drive
SMART data through to the VM. In that case, keep the template linked so a
future passthrough disk is discovered, but monitor the physical disks on the
hypervisor or storage system as well. An empty result is reported as a warning
by the installer rather than treated as an installation failure.

## Intel in-band ECC monitoring

The memory ECC collector reads the Linux EDAC counters from
`/sys/devices/system/edac/mc`. Intel in-band ECC is exposed there by the
`igen6_edac` kernel driver when the processor is supported and IBECC is enabled
in firmware. The installer makes a non-fatal attempt to load this driver before
checking whether EDAC is available.

The template records corrected and uncorrected error totals and discovers
per-controller and per-DIMM counters. Corrected errors remain a warning and
uncorrected errors remain a disaster until the kernel counters reset. The
counters start at driver initialization and may return to zero after a reboot
or driver reload.

The service installer links the memory ECC template automatically.
Its availability trigger reports when no EDAC memory controller is registered,
which commonly means IBECC is disabled in firmware or `igen6_edac` did not
bind to the processor.

Verify the driver and counters on the host:

```bash
sudo modprobe igen6_edac
lsmod | grep igen6_edac
find /sys/devices/system/edac/mc -maxdepth 2 -type f
```

## Collector keys

`zfs.metrics` runs every minute through the template. It reports:

- Tank health, capacity, fragmentation, errors, scrub/resilver state, and I/O counters
- Leaf-vdev state and read, write, and checksum errors
- Used bytes, quotas, and utilization for the five fixed leaf datasets
- Mount, encryption, and key state for `tank/secure`
- ARC and L2ARC size, hit rate, and error counters

Tank capacity warns above 80% and raises a high alert above 90%.
Each fixed leaf dataset raises a high alert at 90% of its quota.
The storage dashboard sorts leaf datasets by utilization and charts used bytes.
Missing or unlimited leaf quotas are collector errors instead of inferred limits.
Permanent ZFS data errors are disasters and unsuccessful scrub results are high alerts.
Repaired scrub damage and recorded pool or vdev errors are persistent warnings.

`zfs.snapshots` runs every 15 minutes. It reports per-dataset snapshot count,
`usedbysnapshots`, and oldest/newest snapshot age. Snapshot names are not sent
to Zabbix, avoiding unbounded item discovery and unnecessary metadata exposure.

`retained_bytes` is the authoritative snapshot-space metric. The
`snapshot_unique_bytes_sum` field is diagnostic only: snapshot blocks can be
shared, so summing individual snapshot `used` values does not necessarily equal
the space freed by deleting every snapshot.

Each fixed leaf reports retained snapshot bytes without a size alert.
Each fixed leaf reports retained snapshot bytes as a percentage of total used space.
Each fixed leaf warns when its oldest snapshot is older than 90 days.
The age threshold uses `{$ZFS.SNAPSHOT.MAX_AGE}`.

## Local tests

Run the collectors with the same permissions as the service:

```bash
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py metrics | python3 -m json.tool
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py snapshots | python3 -m json.tool
sudo -u zabbix /usr/local/libexec/zabbix/memory-ecc-collector.py | python3 -m json.tool
```

Test the registered Agent 2 keys:

```bash
sudo zabbix_agent2 -t zfs.metrics
sudo zabbix_agent2 -t zfs.snapshots
sudo zabbix_agent2 -t memory.ecc.metrics
sudo zabbix_agent2 -t smart.disk.discovery
sudo zabbix_agent2 -t smart.disk.get
```

Inspect service status and logs:

```bash
systemctl status zabbix-agent2.service
sudo journalctl -u zabbix-agent2.service
```

The ZFS and memory ECC collectors have no flexible arguments and invoke no
shell. The `zabbix` user receives no pool-modification, dataset-modification,
encryption-key, EDAC reset, or error-injection permissions. Its additional sudo
access is limited to the documented SMART plugin forms of the root-owned
smartctl wrapper.
