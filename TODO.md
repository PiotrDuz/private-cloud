# Outstanding work

[PLAN.md](PLAN.md) defines the target state; this file tracks repository automation that remains. Initial operator configuration is in [docs/SETUP.md](docs/SETUP.md); ongoing maintenance is in [docs/OPERATIONS.md](docs/OPERATIONS.md).

Backup automation, snapshot retention, and recovery planning are deferred.

## Authentication implementation

- [x] Make Stalwart the shared OIDC provider for OpenCloud, Grist, AFFiNE, and Immich.
- [x] Register the application OAuth clients in Stalwart without separate login allowlists.
- [x] Update issuer routing and add CORS on the Stalwart OAuth endpoints.
- [x] Automate AFFiNE OIDC and bind the OpenCloud administrator to the Stalwart mailbox account.
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
- [ ] Confirm a missing unlock interface wipes the unlock and shows the recovery prompt.
- [ ] Confirm a wipe prints `wiped:` with a verified state and the recovery prompt still accepts the passphrase.
- [ ] Confirm a USB device attached before the tripwire starts trips it against the enrolled device set.
- [ ] Confirm an armed boot with the enrolled devices does not trip the tripwire.
- [ ] Confirm a fresh configuration binds PCR 1 and survives three cold boots.
- [x] Add Zabbix items for the unlock state, Secure Boot state, and tripwire state.
- [ ] Confirm the boot integrity Zabbix items report on an enrolled host and clear after re-enrollment.

## Runtime validation gaps

- [ ] Verify that ZFS unlock and k0s startup succeed after an actual reboot.
- [ ] Validate OpenCloud mobile sign-in through Stalwart.
- [ ] Validate provider claims, confidential clients, callbacks, and supported logout flows.
- [ ] Validate manual disabling, deletion, and re-enabling in each application.
- [ ] Verify account deletion removes user-owned data while disabling preserves it.
- [ ] Verify shared user-owned resources are deleted and other users' resources remain intact.
- [ ] Verify revoked browser sessions, mobile sessions, API keys, refresh tokens, and WebSocket access.
- [ ] Verify ordinary logout leaves the Stalwart account enabled.
- [ ] Validate Stalwart identity and application data recovery together.
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
- [ ] Verify Jellyfin Quick Sync hardware transcoding works under UID 2002 with the render group.
- [ ] Verify Jellyfin starts, plays, and downloads metadata with its read-only root filesystem.
- [ ] Verify Jellyfin reads arr-written library files through media group 2000.
- [ ] Verify a reapply re-owns the existing Jellyfin dataset to UID 2002.
- [ ] Verify Traefik serves every route from route ConfigMaps without Kubernetes API access.
- [ ] Verify the Zabbix route ConfigMap appears only after the administrator password is set.
- [ ] Verify oauth2-proxy login on the Grist host with a fresh Stalwart sign-in.
- [ ] Verify Grist logout through `/oauth2/sign_out` lands on the Stalwart sign-in page.
- [ ] Verify a public route returns the HSTS, nosniff, and referrer policy headers once.
- [ ] Verify OnlyOffice and Draw.io still embed in OpenCloud with the security headers.
- [ ] Verify Stalwart sign-in and app OIDC redirects work with the referrer policy.
- [ ] Verify WOPI proof-key verification between OnlyOffice 9.4.0.1 and OpenCloud 7.2.4.
- [ ] Fall back to `COLLABORATION_APP_PROOF_DISABLE=true` if proof-key verification fails.
- [ ] Verify OnlyOffice rejects a foreign WOPI host.
- [ ] Verify the Draw.io extension installs and opens with OpenCloud 7.2.4.
- [ ] Verify Stalwart indexes and searches through its scoped Meilisearch key.
- [ ] Verify the OpenObserve heartbeat aggregate alert fires when heartbeats stop.
- [ ] Verify Zabbix PSK agent traffic works and a PSK rotation reconnects the agent.
- [ ] Verify a reapply labels every managed namespace with privileged enforcement and baseline auditing.
- [ ] Verify the API server audit log records baseline violations from the namespace labels.
- [ ] Verify an interrupted `create` resumes from the recorded intent.
- [ ] Verify k0s starts and routes with custom pod and service CIDRs.
- [ ] Verify a VPN peer reaches public routes and local-only routes through Traefik's VPN entrypoint.
- [ ] Verify a LAN client reaches Zabbix, OpenObserve, Stalwart `/admin`, and the other local-only routes.
- [ ] Verify an application pod gets HTTP 403 from local-only routes and Stalwart `/admin`.
- [ ] Verify a WAN client gets HTTP 403 from Zabbix, OpenObserve, and Stalwart `/admin` while Stalwart JMAP and OIDC still work.
- [ ] Verify the Stalwart account manager at `/account` still works from WAN with `/admin` restricted.
- [ ] Verify the gluetun 3.41.3 gateway connects, passes health checks, and forwards its port with `hostUsers: false`.
- [ ] Verify qBittorrent reads and writes its dataset and the library as UID 2000 in the gateway user namespace.
- [ ] Verify the gateway mangle rules survive a `wireguard` container restart and qBittorrent stays offline while gluetun is down.
- [ ] Verify gluetun and qBittorrent cannot query cluster DNS on eth0 while the gateway CoreDNS still resolves `cluster.local`.
- [ ] Verify the gateway starts in its user namespace after a host reboot before any other iptables user loads the netfilter modules.
