# Operator record

Complete this record before production use and keep a current offline copy with the recovery material.

`TBD` is a blocking value, not a default.

## Service objectives

| Value | Operator decision |
| --- | --- |
| Maximum data loss for PostgreSQL and associated application files | TBD |
| Maximum recovery time for the whole host | TBD |
| Maximum recovery time for mail | TBD |
| Maximum recovery time for office editing | TBD |
| Backup retention by frequency | TBD |
| Restore exercise interval | TBD |

## Backup custody

| Value | Operator decision |
| --- | --- |
| Independent backup destination | TBD |
| Backup transport and encryption | TBD |
| Backup credential owner | TBD |
| Offline recovery-copy locations | TBD |
| Backup deletion authority | TBD |

The independent destination must survive loss, theft, compromise, and pool failure of the managed host.

## Public edge

| Value | Operator decision |
| --- | --- |
| Public IPv4 and IPv6 addresses | TBD |
| DNS provider and zone owner | TBD |
| Application reverse proxy | TBD |
| TCP 443 owner and ACME challenge method | TBD |
| TLS certificate owner and renewal method | TBD |
| Firewall and NAT owner | TBD |
| Pod-to-public-hostname routing method | TBD |

## Monitoring

| Value | Operator decision |
| --- | --- |
| External heartbeat service | TBD |
| Notification destination | TBD |
| Backup-freshness threshold | TBD |
| Certificate-expiry warning threshold | TBD |
| Restore-readiness owner | TBD |

The heartbeat and notification destinations must remain available when this host, pool, cluster, or PostgreSQL instance is unavailable.

## Host and pool

| Value | Operator decision |
| --- | --- |
| Host hardware model and spare location | TBD |
| Disk models, sizes, and by-id paths | TBD |
| Replacement-disk minimum size | TBD |
| RAIDZ1 acceptance rationale | TBD |
| Expected resilver time and load limit | TBD |
| Boot-media recovery source | TBD |
| k0s local-volume node identity | TBD |

The RAIDZ1 decision must address one-disk parity, disk count, disk size, rebuild exposure, restore objectives, and the independent backup.

## Capacity

| Value | Operator decision |
| --- | --- |
| Host RAM | TBD |
| ZFS ARC minimum and maximum | TBD |
| Host and k0s memory reserve | TBD |
| CPU reserve and overcommit limit | TBD |
| Container-log budget and retention | TBD |
| Container-image budget and pruning threshold | TBD |
| Temporary extraction and upload budget | TBD |
| Per-application PostgreSQL space budgets and alert thresholds | TBD |

## External dependencies

| Value | Operator decision |
| --- | --- |
| inbox.eu account owner and renewal date | TBD |
| inbox.eu relay limits and support contact | TBD |
| Draw.io source availability decision | TBD |
| Repository license | TBD |

The repository does not select a license on the operator's behalf.
