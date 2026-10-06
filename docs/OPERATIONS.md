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

## OpenCloud and OIDC

OpenCloud's built-in provider and directory supply shared login for Grist, AFFiNE, and Immich.

- Manage accounts and groups in the OpenCloud admin area.
- Use unique administrator-controlled email identities for downstream accounts.
- Check discovery at `https://<opencloud-hostname>/.well-known/openid-configuration` after changes.
- Reapply to update enabled client registrations and callback hostnames.
- Keep directory data, signing keys, and generated configuration together during recovery.
- Restore the public configuration and Vault ciphertext from the same recovery point.
- Restore and mount `tank/secure/backup/private-cloud-config` before reapplying.
- The initial OpenCloud administrator password and OIDC client secrets are not rotatable through the installer.
- Rotatable groups cover enabled service database passwords, mail credentials, Cloudflare tokens, and VPN credentials.
- PostgreSQL, Zabbix, and OpenObserve administrator passwords and the ZFS passphrase are not rotatable.

OpenCloud does not attest email verification. AFFiNE's [supported claim mapping](https://github.com/toeverything/AFFiNE/blob/v0.27.3/packages/backend/server/src/plugins/oauth/providers/oidc.ts) for `claim_email_verified` names an absent claim so its supported OIDC mapping accepts administrator-controlled email identities; administrators must keep these addresses unique and prevent reassignment while downstream accounts exist.

## Account deletion

Account deletion is manual in each application; OIDC does not synchronize account or data deletion.

- Disable the user in OpenCloud and each application where they have an account.
- Revoke their sessions, API keys, and refresh tokens through each application's supported controls.
- Delete their accounts and user-owned data in each application.
- Remove owned documents, workspaces, attachments, and media explicitly when account deletion leaves them behind.
- Preserve resources owned by other users while removing the deleted user's memberships.
- Confirm asynchronous data deletion completes before closing the task.
- Complete deletion in OpenCloud after downstream cleanup.

### Application cleanup

| Application | Disable while preserving data | Delete account and revoke credentials |
| --- | --- | --- |
| OpenCloud | Disable the account in the admin area. | Remove owned spaces and files, shares, app passwords, and sessions before deleting the user. |
| Grist | Disable OpenCloud login and remove site access. | Delete owned documents and API keys, remove memberships, and delete the Grist account after resolving ownership. |
| AFFiNE | Disable OpenCloud login and remove workspace access. | Delete owned workspaces and attachments, revoke sessions and tokens, and delete the AFFiNE account. |
| Immich | Disable OpenCloud login and revoke active sessions. | Revoke API keys and devices, delete the user in Administration, and confirm the queued library deletion completes. |
| Stalwart | Deny authentication permissions while retaining mailbox data. | Revoke app passwords and API keys, delete the account and aliases, and confirm mail and blob cleanup completes. |
| Jellyfin | Disable the user in the dashboard. | Revoke devices, sessions, and applicable API keys, then delete the user while preserving the shared media library. |
| ARR, Zabbix, OpenObserve | Disable or remove access through native controls. | Revoke native credentials and tokens and remove personal resources through each service's controls. |
| AmneziaWG | Remove peer access from the public configuration. | Remove the peer and reapply to revoke its key. |

- Remove shared resources owned by the deleted user after identifying their owner.
- Preserve resources owned by other users and remove only the departing user's access.
- Record native permissions before temporarily suspending a Stalwart mailbox.
- Confirm browser, mobile, API, refresh-token, and WebSocket access is revoked.
- Validate each application's cleanup behavior on the deployed version.

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

When notifications are enabled, Zabbix sends Warning-or-higher problems, recoveries, and hourly reminders. OpenObserve evaluates recognized warning, error, and critical logs every minute and suppresses repeated notifications for sixty minutes, matching the hourly Zabbix reminders. A single matching log entry can trigger an alert.

Alerts go directly to Stalwart's internal SMTP listener on TCP 2525 without TLS or authentication. Network policies permit OpenObserve and Zabbix to reach this listener, and anonymous external relaying remains disabled. Global validation sends a test message over this path and confirms its arrival in the Stalwart mailbox over JMAP.

OpenObserve excludes its own logs from severity alerts, and Zabbix does not probe its application health or search API. OpenObserve outages and notification failures require direct inspection or independent monitoring.

| Check | Where to investigate |
| --- | --- |
| Missing Zabbix email | Reports → Action log, trigger actions, SMTP media, recipient permissions, and severity selection. |
| Missing OpenObserve email | Alert state, destination, silence period, SMTP settings, and OpenObserve logs. |
| Email accepted but absent from inbox | Internal SMTP service, network policies, and Stalwart delivery or filtering logs. |
| Repeated log alerts | OpenObserve query, affected service, and dependency logs. |

- Verify warning and recovery delivery after changing rules, credentials, or routing.
- Confirm delivery in the inbox rather than relying on SMTP acceptance.
- Check that maintenance silences expire as intended.
- Use dashboard checks during mail failures because Stalwart cannot report its own complete outage.
- Use independent monitoring for host, Internet, or mailbox outages.

## Recovery

Backup automation and independent outage monitoring are not configured by this repository. Sonarr, Radarr, Prowlarr, qBittorrent, and the shared media library use `no-backup` datasets and are outside backup scope.

- Check independent backup completion and age against the chosen schedule.
- Keep PostgreSQL and application-file recovery points consistent.
- Keep encryption keys and configuration recovery material outside this host.
- Periodically restore an independent backup and record the result.
- After reboot, confirm datasets are mounted, pods are ready, and monitoring has resumed.
