# Outstanding work

[PLAN.md](PLAN.md) defines the target state; this file tracks repository automation that remains. Operator tasks are in [docs/SETUP.md](docs/SETUP.md).

Backup automation, snapshot retention, and recovery planning are deferred.

## Runtime validation gaps

- [ ] Verify that ZFS unlock and k0s startup succeed after an actual reboot.
- [ ] Automate full OIDC sign-in and logout flows with test users for each application.
- [ ] Automate Jellyfin SSO-OIDC Quick Connect and role-mapping checks.
- [ ] Automate Keycloak realm recreation and post-recreation checks.
- [ ] Validate split DNS from LAN and VPN clients.
- [ ] Validate ARR API connections and library-folder access.
- [ ] Validate Jellyfin library scans, playback, and metadata downloads.
- [ ] Validate certificate issuance and renewal, not only current trust.
- [ ] Validate forwarding-domain MX and mail authentication DNS records.
- [ ] Validate host firewall reachability from WAN and local networks.

## Observability validation gaps

- [ ] Check timestamped log ingestion for every enabled service and host source.
- [ ] Report live unclassified log formats that need severity parsing.
- [ ] Exercise collector restart and bounded OpenObserve outage recovery.
- [ ] Verify source rotation and expired OpenObserve data deletion.
- [ ] Trigger each managed warning, error, critical, and Kubernetes Warning rule.
- [ ] Verify Zabbix hourly reminder delivery while a problem stays open.
- [ ] Exercise OpenObserve missing-heartbeat and Zabbix Alloy health alerts.
- [ ] Verify collector failure logs reach OpenObserve for ZFS, ECC, and SMART.
- [ ] Verify OpenObserve query and SMTP failures appear in logs and alerts.
- [ ] Validate media VPN and Jellyfin isolation from logging access.
