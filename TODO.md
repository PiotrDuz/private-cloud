# Outstanding work

[PLAN.md](PLAN.md) defines the target state; this file tracks repository automation that remains. Initial operator configuration is in [docs/SETUP.md](docs/SETUP.md); ongoing maintenance is in [docs/OPERATIONS.md](docs/OPERATIONS.md).

Backup automation, snapshot retention, and recovery planning are deferred.

## Authentication implementation

- [x] Replace the identity installer configuration with OpenCloud's built-in services.
- [x] Register OpenCloud, Grist helper, AFFiNE, and Immich clients without separate login allowlists.
- [x] Update OIDC network policies and issuer routing to OpenCloud.
- [x] Replace Stalwart OIDC configuration with native mailbox authentication.
- [x] Remove Jellyfin SSO installation and configure native password login.
- [x] Update setup documentation and monitoring inventory for the new authentication target.
- [x] Define manual native account deletion and data removal in the operations runbook.
- [x] Document application-specific account deletion and credential revocation in the operations runbook.

## Runtime validation gaps

- [ ] Verify that ZFS unlock and k0s startup succeed after an actual reboot.
- [ ] Validate OpenCloud, Grist, AFFiNE, and Immich sign-in with the built-in provider.
- [ ] Validate provider claims, confidential clients, callbacks, and supported logout flows.
- [ ] Validate email-based sign-in with OpenCloud's unverified email claims.
- [ ] Validate manual disabling, deletion, and re-enabling in each application.
- [ ] Verify account deletion removes user-owned data while disabling preserves it.
- [ ] Verify shared user-owned resources are deleted and other users' resources remain intact.
- [ ] Verify revoked browser sessions, mobile sessions, API keys, refresh tokens, and WebSocket access.
- [ ] Verify ordinary logout leaves the OpenCloud account enabled.
- [ ] Validate OpenCloud identity configuration and data recovery together.
- [ ] Validate Jellyfin password login and native Quick Connect.
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
