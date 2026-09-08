# Operations

Loki, Alloy, Grafana, and email notifications are planned but not configured. Their runtime checks below apply after the [implementation and acceptance steps](../PLAN.md#implementation-and-acceptance--pending) are complete.

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
| Logging health, once implemented | Loki/Grafana availability, collector heartbeat, delivery lag, and dropped entries. | Investigate missing collection even when applications are quiet. |

- Check timestamps and unsupported items when metrics disappear.
- Use ZFS quota utilization rather than advertised 10Ti PV capacity.
- Watch PostgreSQL growth because applications share its dataset.
- Check all enabled datasets because the capacity widget displays only the top seven.

## Incidents and logs

- Check pod readiness, restarts, and events when an application fails.
- In Grafana Explore, select Loki and filter by service, container, and incident time.
- Include surrounding messages when investigating a warning or error.
- Correlate failures with resource pressure, deployments, and dependency outages.
- Include qBittorrent's `file-logs` container when inspecting its application messages.
- Check Jellyfin FFmpeg diagnostics under `/config/log` for transcoding failures.

```bash
sudo k0s kubectl get pods -A
sudo k0s kubectl get events -A --sort-by=.metadata.creationTimestamp
sudo k0s kubectl logs -n private-cloud statefulset/stalwart --since=1h --tail=500
sudo k0s kubectl logs -n edge deployment/traefik --since=1h --tail=500
sudo k0s kubectl logs -n media deployment/qbittorrent -c file-logs --since=1h --tail=500
sudo journalctl -u k0scontroller.service --since='1 hour ago'
```

Use `kubectl logs --previous` with the affected pod and container after a crash.

Once central logging is deployed:

- Investigate Alloy retries, rejected entries, dropped logs, and missing heartbeats.
- Confirm Loki removes expired chunks after the 14-day retention period and deletion delay.
- Check Loki and Alloy quotas before buffers or storage fill.
- Check container rotation, host journal limits, and application file rotation separately.

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

After notification deployment, Zabbix Warning-or-higher problems and Grafana warning-or-higher log alerts must arrive in the Stalwart inbox, with recovery messages. A single warning log entry triggers an alert; repeated lines in an active alert produce reminders rather than individual emails.

| Check | Where to investigate |
| --- | --- |
| Missing Zabbix email | Reports → Action log, trigger actions, SMTP media, recipient permissions, and severity selection. |
| Missing Grafana email | Alert rule state, contact point, notification policy, silences, and Grafana SMTP logs. |
| Email accepted but absent from inbox | External relay queue, forwarding-domain MX, Traefik SMTP, and Stalwart delivery or filtering logs. |
| Repeated log alerts | Linked Loki query, affected service, and dependency logs. |

- Verify warning and recovery delivery after changing rules, credentials, or routing.
- Confirm delivery in the inbox rather than relying on SMTP acceptance.
- Check that maintenance silences expire as intended.
- Use dashboard checks during mail failures because Stalwart cannot report its own complete outage.

## Recovery

Backup automation and independent outage monitoring are not configured by this repository.

- Check independent backup completion and age against the chosen schedule.
- Keep PostgreSQL and application-file recovery points consistent.
- Keep encryption keys and configuration recovery material outside this host.
- Periodically restore an independent backup and record the result.
- After reboot, confirm datasets are mounted, pods are ready, and monitoring has resumed.
