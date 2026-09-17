# Outstanding work

[PLAN.md](PLAN.md) defines the target state; unchecked items here remain to be implemented in the repository. Operator-only work is tracked in [docs/SETUP.md](docs/SETUP.md).

Backup automation, snapshot retention, and recovery planning are deferred.

## Startup and storage verification automation

- [ ] Automate post-reboot verification of ZFS unlock, mount, and k0s startup ordering.

## Identity verification automation

- [ ] Automate end-to-end OIDC login verification for every Keycloak-backed service.
- [ ] Automate Jellyfin SSO-OIDC plugin login, Quick Connect, and role-mapping validation.
- [ ] Automate the Keycloak realm recreation procedure and its post-recreation client checks.
- [ ] Automate split-DNS resolution verification for LAN and VPN clients.

## Service verification automation

- [ ] Automate ARR connection, API, and library-folder verification after deployment.
- [ ] Automate Jellyfin library scan, playback, and metadata download verification after deployment.
- [ ] Automate Stalwart JMAP and basic-auth verification.
- [ ] Automate Traefik and Stalwart certificate issuance and renewal verification.
- [ ] Automate Cloudflare public A record creation and forwarding-domain MX reconciliation.
- [ ] Automate SPF, DKIM, and DMARC publication and DNS verification.
- [ ] Automate host-side firewall and route checks from the deployment acceptance matrix.

## Logging and notification acceptance automation

- [ ] Automate the timestamped-log presence check for every enabled service and host source in OpenObserve.
- [ ] Automate reporting of live unclassified log formats that need severity parsing.
- [ ] Automate collector-restart and bounded OpenObserve outage recovery checks.
- [ ] Automate source rotation and expired OpenObserve data deletion checks.
- [ ] Automate synthetic log warning, log error, and Kubernetes Warning notification checks.
- [ ] Automate Zabbix Warning-or-higher problem and recovery email checks.
- [ ] Automate OpenObserve missing-heartbeat and Zabbix Alloy health alert checks.
- [ ] Automate Zabbix Agent and ZFS, ECC, and SMART collector failure ingestion checks.
- [ ] Automate OpenObserve query and SMTP failure visibility checks.
- [ ] Automate media VPN and Jellyfin isolation checks for logging access.
