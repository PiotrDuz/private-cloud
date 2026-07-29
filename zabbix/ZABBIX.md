# Zabbix Agent 2 and OpenZFS monitoring

This directory contains a host-side Zabbix Agent 2 installer, the native SMART
plugin setup, and two read-only OpenZFS collectors. It targets Ubuntu 26.04 and
Zabbix Agent 2 7.0 LTS.

## Architecture

Run `zabbix-agent2` as a system service on the ZFS host. Run Zabbix Server
7.4.12, PostgreSQL, and the web frontend in Kubernetes. The agent uses active
checks through the Zabbix Server NodePort. It listens only on `127.0.0.1` for
passive checks.

ZED and the monthly scrub timer remain separate. Zabbix observes their results;
it does not replace local ZFS event processing or initiate scheduled scrubs.
The Agent 2 SMART plugin uses `smartmontools` to monitor physical drives when
the storage controller exposes SMART data to the operating system.

## Install

The Zabbix host name supplied here must exactly match the host name configured
in the Zabbix frontend.

Install ZFS, k0s, and PostgreSQL first.
Deploy the Zabbix Kubernetes service before the host agent:

```bash
sudo python3 ./k0s-services/zabbix/install.py
```

The installer uses NodePort `31051` for Zabbix Server and `30080` for the web
frontend. Replace `10.0.0.20` below with the k0s node address.

Recommended TLS PSK setup:

```bash
sudo python3 ./zabbix/install.py \
  --server-active 10.0.0.20:31051 \
  --hostname piotr-server-test \
  --psk-identity piotr-server-test-zabbix
```

If Kubernetes is not ready yet, wait to run the installer until the final
Zabbix Server address is known. Rerunning the installer is supported. An
existing PSK file is never overwritten.

Plaintext mode must be explicitly requested and should only be used temporarily
on a trusted lab network:

```bash
sudo python3 ./zabbix/install.py \
  --server-active 10.0.0.20:31051 \
  --hostname piotr-server-test \
  --allow-plaintext
```

The installer creates a backup of the package configuration at
`/etc/zabbix/zabbix_agent2.conf.pre-private-cloud` before its first change.

## Zabbix host configuration

For PSK mode, configure the Zabbix host with:

- Connections from host: PSK
- PSK identity: the value passed to `--psk-identity`
- PSK: output from `sudo cat /etc/zabbix/zabbix_agent2.psk`
- Host name: the exact value passed to `--hostname`

Link these templates:

- `Linux by Zabbix agent active`
- `SMART by Zabbix agent active 2`
- `ZFS by Zabbix agent active` from `zabbix-zfs-template.yaml`

Zabbix Server is reachable at `<node-address>:31051`.
The frontend is separately reachable at `http://<node-address>:30080`.
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

## Collector keys

`zfs.metrics` runs every minute through the template. It reports:

- Pool health, capacity, fragmentation, errors, scrub/resilver state, and I/O
  counters
- Leaf-vdev state and read, write, and checksum errors
- Dataset allocation breakdown, compression, quotas, encryption state, and
  mount state
- ARC and L2ARC size, hit rate, and error counters

`zfs.snapshots` runs every 15 minutes. It reports per-dataset snapshot count,
`usedbysnapshots`, and oldest/newest snapshot age. Snapshot names are not sent
to Zabbix, avoiding unbounded item discovery and unnecessary metadata exposure.

`retained_bytes` is the authoritative snapshot-space metric. The
`snapshot_unique_bytes_sum` field is diagnostic only: snapshot blocks can be
shared, so summing individual snapshot `used` values does not necessarily equal
the space freed by deleting every snapshot.

## Local tests

Run the collectors with the same permissions as the service:

```bash
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py metrics | python3 -m json.tool
sudo -u zabbix /usr/local/libexec/zabbix/zfs-collector.py snapshots | python3 -m json.tool
```

Test the registered Agent 2 keys:

```bash
sudo zabbix_agent2 -t zfs.metrics
sudo zabbix_agent2 -t zfs.snapshots
sudo zabbix_agent2 -t smart.disk.discovery
sudo zabbix_agent2 -t smart.disk.get
```

Inspect service status and logs:

```bash
systemctl status zabbix-agent2.service
sudo journalctl -u zabbix-agent2.service
```

The ZFS collector has no flexible arguments and invokes no shell. The `zabbix`
user receives no pool-modification, dataset-modification, or encryption-key
permissions. Its additional sudo access is limited to the documented SMART
plugin forms of the root-owned smartctl wrapper.
