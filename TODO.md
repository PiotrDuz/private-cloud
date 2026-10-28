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

## Boot integrity acceptance

- [ ] Build the initrd with the dracut module and list its contents with `lsinitrd`.
- [ ] Boot the signed UKI under Secure Boot and confirm the recovery prompt on the first armed-less boot.
- [ ] Enroll the unlock and confirm an unattended reboot unlocks root and k0s.
- [ ] Confirm the initrd wipes the unlock and powers off after 2 minutes without a gateway answer.
- [ ] Confirm a router that answers within 2 minutes still lets the host unlock.
- [ ] Confirm a wrong gateway MAC wipes the unlock and the next boot runs no checks.
- [ ] Confirm an attached USB device wipes the unlock and powers the host off at runtime.
- [ ] Confirm a USB keyboard works at the recovery prompt after a wipe.
- [ ] Confirm console login works only after a wipe.
- [ ] Confirm held packages and the unattended-upgrades blacklist keep the booted kernel installed.
- [ ] Confirm Zabbix, Alloy, and Intel GPU workloads run under kernel lockdown.
- [ ] Add Zabbix items for the unlock state, Secure Boot state, and tripwire state.

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
- [x] Validate split DNS from the host.
- [ ] Validate LAN DNS from other LAN clients and VPN clients.
- [ ] Verify Firefox and Apple devices fall back to the LAN resolver through the canaries.
- [ ] Verify cluster DNS keeps resolving after a `lan-dns` pod restart.
- [ ] Validate ARR API connections and library-folder access.
- [ ] Validate Jellyfin library scans, playback, and metadata downloads.
- [x] Require publicly trusted certificates with more than 14 days remaining.
- [ ] Observe a completed Let's Encrypt renewal for Traefik and Stalwart.
- [x] Validate primary-domain MX, SPF, and DMARC records through public resolvers.
- [ ] Validate the provider-specific DKIM record.
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
- [ ] Verify the AirVPN WireGuard tunnel fails closed when the endpoint is unreachable.

## Hardening validation gaps

- [ ] Obtain a real Let's Encrypt certificate through Traefik with the public DNS 53 egress.
- [ ] Verify OIDC discovery, token exchange, and WOPI callbacks reach the Traefik pod on TCP 8443.
- [ ] Verify the installer claims Immich, AFFiNE, and Jellyfin administrators before their routes are published.
- [ ] Verify Traefik serves every route from route ConfigMaps without Kubernetes API access.
- [ ] Verify the Zabbix route ConfigMap appears only after the administrator password is set.
- [ ] Verify oauth2-proxy login on the Grist host with a fresh OpenCloud session.
- [ ] Verify Grist logout through `/oauth2/sign_out` ends the OpenCloud session and lands on the sign-in page.
- [ ] Verify the OpenCloud end-session path and `id_token_hint` handling with OpenCloud 7.2.4.
- [ ] Verify WOPI proof-key verification between OnlyOffice 9.4.0.1 and OpenCloud 7.2.4.
- [ ] Fall back to `COLLABORATION_APP_PROOF_DISABLE=true` if proof-key verification fails.
- [ ] Verify OnlyOffice rejects a foreign WOPI host.
- [ ] Verify the Draw.io extension installs and opens with OpenCloud 7.2.4.
- [ ] Verify Stalwart indexes and searches through its scoped Meilisearch key.
- [ ] Verify the OpenObserve heartbeat aggregate alert fires when heartbeats stop.
- [ ] Verify Zabbix PSK agent traffic works and a PSK rotation reconnects the agent.
- [ ] Verify an interrupted `create` resumes from the recorded intent.
- [ ] Verify k0s starts and routes with custom pod and service CIDRs.
