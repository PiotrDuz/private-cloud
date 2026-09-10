# Operations

Repository configuration installs OpenObserve, Alloy, Zabbix monitoring, and optional email notifications. This runbook does not prove a live deployment, email delivery, or external reachability.

## Monitoring

Open Zabbix at `networking.zabbix_hostname` and review **Monitoring → Problems** for `private-cloud-zabbix`.

| View | Critical checks | Response |
| --- | --- | --- |
| Private cloud ZFS storage → Dataset capacity | Quota utilization and current leaf allocation. | Investigate at 80%; act before 90%. |
| Latest data → ZFS pool | Usage, online state, permanent errors, and read/write/checksum errors. | Prioritize degraded storage, permanent errors, and 90% usage. |
| Latest data → Linux | CPU, available RAM, swap, disk latency, and filesystem space. | Investigate sustained saturation and growing pressure. |
| Latest data → SMART | Health, temperature, and media errors. | Investigate failing health and rising errors. |
| Latest data → Memory ECC | Corrected and uncorrected errors. | Prioritize uncorrected errors and repeated corrections. |
| Latest data → ZFS scrub | Last completion, repaired bytes, and remaining errors. | Investigate failures or no completed scrub for 40 days. |
| Latest data → ZFS snapshots | Retained bytes, oldest age, and collector errors. | Check growth and age against the chosen retention schedule. |
| Alloy health | Collector availability, metrics availability, retries, and dropped entries. | Investigate unhealthy collection and delivery pressure. |

- Check timestamps and unsupported items when metrics disappear.
- Use ZFS quota utilization rather than advertised 10Ti PV capacity.
- Watch PostgreSQL growth because applications share its dataset.
- Check all enabled datasets because the capacity widget displays only the top seven.
- Reapply the configuration after an SMTP relay IP change to refresh egress allowlists.

## Incidents and logs

- Check pod readiness, restarts, and events when an application fails.
- In OpenObserve, select the `logs` stream and filter by service, container, level, and incident time.
- Include surrounding messages when investigating a warning or error.
- Correlate failures with resource pressure, deployments, and dependency outages.
- Include qBittorrent's `file-logs` container when inspecting its application messages.
- Filter host collector errors by private-cloud-zabbix-* service names in OpenObserve.
- Filter Zabbix Agent journal logs by the zabbix-agent2.service service name.
- Check Jellyfin FFmpeg diagnostics under `/config/log` for transcoding failures.
- Treat unclassified logs as evidence for investigation even when no log alert fires.
- Search historical logs after an outage because delayed entries outside the five-minute alert window do not trigger log alerts.

```bash
sudo k0s kubectl get pods -A
sudo k0s kubectl get events -A --sort-by=.metadata.creationTimestamp
sudo k0s kubectl logs -n private-cloud statefulset/stalwart --since=1h --tail=500
sudo k0s kubectl logs -n edge deployment/traefik --since=1h --tail=500
sudo k0s kubectl logs -n media deployment/qbittorrent -c file-logs --since=1h --tail=500
sudo journalctl -u k0scontroller.service --since='1 hour ago'
```

Use `kubectl logs --previous` with the affected pod and container after a crash.

- Investigate Alloy retries, rejected entries, dropped logs, and missing heartbeats.
- Check missing-heartbeat alerts in OpenObserve and Alloy health in Zabbix.
- Inspect OpenObserve query, ingestion, and notification failures directly through its logs and interface.
- Confirm OpenObserve removes expired data after the 14-day retention period.
- Check OpenObserve and Alloy quotas before storage or buffers fill.
- Check the ephemeral kubelet quota because CRI logs use `/tank/secure/k0s/kubelet/logs`.
- Check container rotation, host journal limits, qBittorrent and OnlyOffice rotation, and FFmpeg pruning separately.

## Certificates and mail

Traefik renews HTTPS certificates automatically; Stalwart renews its SMTP STARTTLS certificate independently through Cloudflare DNS-01.

| Weekly check | What to inspect |
| --- | --- |
| Traefik HTTPS | Expiry and hostname validity on each application hostname at TCP 443. |
| Stalwart SMTP | Expiry and hostname validity using STARTTLS on the mail hostname at TCP 25. |
| Renewal logs | ACME failures, DNS challenge errors, and rejected Cloudflare tokens. |
| Mail delivery | Delivery queues, relay failures, forwarding failures, and rejected recipients. |

- Investigate certificates with fewer than 21 days remaining and no successful renewal.
- Treat fewer than 7 days remaining as urgent.
- Check the affected service's Cloudflare token and outbound connectivity after renewal failures.
- Check SMTP separately because the mail website presents Traefik's certificate.

## Email alerts

When notifications are enabled, Zabbix sends Warning-or-higher problems, recoveries, and hourly reminders. OpenObserve evaluates recognized warning, error, and critical logs every minute and suppresses repeated notifications for five minutes. A single matching log entry can trigger an alert.

OpenObserve excludes its own logs from severity alerts, and Zabbix does not probe its application health or search API. OpenObserve outages and notification failures require direct inspection or independent monitoring.

| Check | Where to investigate |
| --- | --- |
| Missing Zabbix email | Reports → Action log, trigger actions, SMTP media, recipient permissions, and severity selection. |
| Missing OpenObserve email | Alert state, destination, silence period, SMTP settings, and OpenObserve logs. |
| Email accepted but absent from inbox | External relay queue, forwarding-domain MX, Traefik SMTP, and Stalwart delivery or filtering logs. |
| Repeated log alerts | OpenObserve query, affected service, and dependency logs. |

- Verify warning and recovery delivery after changing rules, credentials, or routing.
- Confirm delivery in the inbox rather than relying on SMTP acceptance.
- Check that maintenance silences expire as intended.
- Use dashboard checks during mail failures because Stalwart cannot report its own complete outage.
- Use independent monitoring for host, Internet, or mailbox outages.

## Recovery

Backup automation and independent outage monitoring are not configured by this repository.

- Check independent backup completion and age against the chosen schedule.
- Keep PostgreSQL and application-file recovery points consistent.
- Keep encryption keys and configuration recovery material outside this host.
- Periodically restore an independent backup and record the result.
- After reboot, confirm datasets are mounted, pods are ready, and monitoring has resumed.
