# Repository review and conversation findings

Static review only; findings and proposed resolutions below are not implemented or verified on a live host.
The initial review excluded external integrations; later discussion covered ZFS recovery and home DNS wiring.

## Security, networking, and data integrity

| Finding | Potential resolution |
| --- | --- |
| Traefik has cluster-wide secret read access through its ClusterRoleBinding. | Scope secret access with namespace RoleBindings and retain only necessary cluster-wide permissions. |
| Sonarr, Radarr, and Prowlarr use default rolling updates against shared persistent configuration. | Use `Recreate` to prevent overlapping instances and conflicting database operations during updates. |
| k0s requires its runtime mounts but not every service dataset mount. | Require and verify service dataset mounts before workload startup to prevent writes into underlying directories. |
| Firewall and VPN templates use configured network ranges that the k0s role neither applies nor compares. | Use repository-owned constants consistently in k0s and templates, with overlap and effective-value checks. |
| Firewall ordering does not require successful firewall startup before k0s. | Add an explicit startup requirement and reload rules without removing the active table first. |
| The host firewall accepts all pod-CIDR traffic to host listeners. | Restrict pod-to-host access to required flows instead of relying on NetworkPolicy alone. |
| Prerouting drops new incoming ICMP before later input allowances. | Put intended ICMP exceptions before the early drop and document any deliberate ping restriction. |
| PostgreSQL initialization explicitly disables data checksums. | Enable PostgreSQL page checksums as an additional corruption-detection layer. |
| Local snapshots, retention, and recovery planning are deferred. | Define coordinated recovery points and rehearse restoration from external ZFS backups. |

`full_page_writes=off` is not automatically unsafe here: PostgreSQL uses an 8K ZFS record size, matching the documented ZFS atomic-write tuning condition.
Scrubs detect storage damage but cannot undo valid application writes or accidental deletion.
ReadWriteOnce limits volume access by node, not by pod.

## Firewall purpose and current behavior

| Source | Allowed incoming traffic |
| --- | --- |
| Any source | TCP 443, TCP 25, and the configured AmneziaWG UDP port. |
| Configured LAN networks | TCP 22, TCP 6443, and TCP 31051. |
| Pod CIDR | All host ports. |
| Existing connections | Established replies and related traffic. |
| DHCP server | UDP replies from port 67 to port 68. |

Other new traffic to the host on the default interface is dropped.
Direct incoming forwarding to pod and Service ranges is blocked unless associated with an approved marked connection.

- Keep the host firewall even behind NAT to restrict access from LAN devices.
- NAT does not replace host protection against forwarding changes or routed IPv6.
- Keep NetworkPolicies for pod communication alongside the host firewall.
- ICMP supports diagnostics, unreachable errors, and path-MTU discovery.
- ICMPv6 also supports essential IPv6 network functions.
- The established/related exception still admits recognized ICMP replies and errors.
- The ICMP finding does not establish that all ICMP or path-MTU discovery fails.

## Cluster addresses and DNS

Applications should use Kubernetes Service names rather than individual pod IPs.
DNS still depends on cluster address allocation and a reachable resolver.

| Setting | Purpose |
| --- | --- |
| Pod CIDR | Addresses allocated to pods. |
| Service CIDR | Virtual addresses allocated to Services. |
| Cluster DNS IP | Resolver address used inside the cluster. |

- Prefer hardcoded repository values, as selected during the conversation.
- Apply those values before initial cluster startup and verify them on reapply.
- Validate that cluster ranges do not overlap LAN or VPN networks.
- Keep firewall and VPN routing rules aligned with the effective cluster ranges.
- Treat changing an existing cluster's ranges as a separate operation.

## Recovery from external ZFS backups

| Dataset or material | Recovery role |
| --- | --- |
| `tank/secure/backup/k0s/config` | k0s data directory, cluster database, certificates, and `k0s.yaml`. |
| `tank/secure/backup/k0s/services/*` | Persistent application databases, files, media, and Traefik state. |
| `tank/secure/no-backup/*` | Disposable runtime storage, images, OpenObserve history, and Alloy state. |
| Matching repository revision and configuration files | Reproducible host and application configuration. |
| Vault password and encryption credentials | Access to configuration secrets and encrypted backups. |

The config dataset mounts at `/tank/secure/k0s`, despite its `backup/k0s/config` dataset name.
Dataset replication includes it; copying only the `/tank/secure/backup` directory would miss it.
The repository does not ensure its public configuration and Vault ciphertext files reside in backed-up storage.

1. Install compatible Ubuntu with the original hostname and preferably the original IP.
2. Recover the matching repository, public configuration, Vault ciphertext, and credentials.
3. Prepare the replacement pool while keeping cloud services stopped.
4. Receive a coordinated set of ZFS backups into the intended dataset layout.
5. Restore and verify encryption roots, key locations, mountpoints, quotas, and ownership.
6. Recreate disposable datasets and install the matching k0s version and host dependencies.
7. Recover cluster state before permitting workload startup.
8. Verify application data, networking, and reboot behavior.

- Restore datasets before startup instead of overwriting a running fresh installation.
- Preserve the original decryption credentials for encrypted raw ZFS backups.
- Account for encryption-root inheritance when receiving only the backup subtree.
- Capture coordinated snapshots rather than sequential copies of live database files.
- Quiesce applications where database and file consistency requires it.
- Consider storing a native k0s backup archive alongside the dataset backups.
- Keep recovery credentials available independently of the failed host.
- Retain access to the pinned binaries and images needed for rebuilding.

A consistent, complete cluster-state restore normally recovers applied Kubernetes objects without reapplying service YAML.
Application PV contents must still be restored separately, and host services, firewall rules, and kernel modules must be recreated.
Native k0s backup archives cover cluster state but not application PV contents.

The current installer has no restore mode: `create` initializes storage, while `reapply` cannot bootstrap a missing pool without create authorization.
A proposed restore workflow must prepare the host, receive and validate storage, recover cluster state, and only then allow startup.

## Access from home Wi-Fi

- Use existing HTTPS service names that resolve locally to the server's LAN IP.
- Traefik selects the application using the requested hostname.
- Direct HTTPS access by server IP generally lacks a matching route and certificate.
- Public-IP resolution from the LAN depends on router NAT loopback.
- Guest Wi-Fi isolation can prevent access to the server.
- Published services are accessible without a VPN when the LAN permits access.
- ARR and qBittorrent dashboards currently have no published Traefik routes.

## Laptop and ASUS RT-AX55 DNS

- Advertise the local resolver through the router's LAN DHCP DNS setting.
- Alternatively, configure DNS in the laptop's Wi-Fi connection settings.
- Custom browser DNS-over-HTTPS and VPN DNS can override system DNS.
- Avoid advertising a public secondary resolver without the same local records.
- Reconnect clients or renew their DHCP leases after changing DNS settings.

On ASUS, use **LAN → DHCP Server → DNS and WINS Server Setting**.
Enter the resolver's LAN IP and disable **Advertise router's IP in addition to user specified DNS**, if available.
ASUS documents that toggle for firmware newer than `3.0.0.4.388.22525`; availability depends on installed firmware.
Advertising a resolver does not create local DNS records.

## Proposed LAN DNS service in k0s

Deploy a separate CoreDNS instance in `dns-system` with local records generated from the existing Traefik hostnames.
Keep the existing Kubernetes DNS service responsible for internal cluster names.

```text
Laptop -> server LAN IP:53 -> LAN CoreDNS
                               |-- service names -> server LAN IP
                               `-- other names -> upstream DNS

Laptop -> server LAN IP:443 -> Traefik -> application
```

- Store local records and forwarding configuration in a ConfigMap.
- Expose TCP and UDP 53 through hostPort bound to the LAN address.
- Check for existing port-53 listeners before deployment.
- Allow LAN DNS before the host firewall's prerouting drop.
- Add NetworkPolicies for DNS ingress and selected upstream resolvers.
- Configure ASUS DHCP to advertise the server's LAN IP.
- Use explicit upstream IPs to avoid DNS forwarding loops.
- Keep host DNS independent so image downloads work before cluster DNS starts.
- Avoid Kubernetes API permissions when records are generated from configuration.
- Use a second resolver on another device if DNS must survive host failure.

The current repository does not provide this LAN resolver or its firewall allowances.
Using a resolver on this single host makes client Internet DNS dependent on host and cluster availability.

## Reference documentation

- [Kubernetes NetworkPolicies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Kubernetes persistent-volume access modes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [PostgreSQL data checksums](https://www.postgresql.org/docs/18/checksums.html)
- [OpenZFS workload tuning](https://openzfs.github.io/openzfs-docs/Performance%20and%20Tuning/Workload%20Tuning.html)
- [OpenZFS snapshots](https://openzfs.github.io/openzfs-docs/Basic%20Concepts/Datasets/Snapshots%20and%20Clones.html)
- [k0s backup and restore](https://docs.k0sproject.io/stable/backup/)
- [ASUS DHCP configuration](https://www.asus.com/us/support/faq/1011703/)
- [ASUS router DNS advertisement](https://www.asus.com/global/support/faq/1050080/)
- [CoreDNS hosts](https://coredns.io/plugins/hosts/)
- [CoreDNS forwarding](https://coredns.io/plugins/forward/)
