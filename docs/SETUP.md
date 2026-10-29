# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## Host installation

- [ ] Install Ubuntu 26.04 LTS with "Use LVM and encryption" on the system disk.
- [ ] Do not select hardware-backed TPM encryption; the TPM design is in [TPM_ANALYSIS.md](TPM_ANALYSIS.md).
- [ ] Use a long random LUKS passphrase and store it offline as the recovery passphrase.
- [ ] Keep the `tank` pool disks out of the installer's partitioning.
- [ ] Give the Ubuntu administrator account a long random password; the console accepts it only after a TPM wipe.
- [ ] Install the collections and run the installer from an interactive root terminal:

```bash
sudo ansible-galaxy collection install -r ansible/requirements.yml
sudo python3 ansible/install.py
```

- [ ] Do not use the installer for unattended operating-system or OpenZFS upgrades.

## Reboot verification

- [ ] Reboot the host under supervision after the first successful installation.
- [ ] Reapply the configuration after reboot to verify native ZFS mounts and k0s ordering.
- [ ] Select `validate` in the installer to check the installed system and alert delivery.

## Boot integrity

The `boot_integrity` stage implements the TPM unlock described in [TPM_ANALYSIS.md](TPM_ANALYSIS.md).

### Firmware settings

- [ ] Set a firmware administrator password.
- [ ] Disable USB, PXE, and network boot; with a USB system disk, allow only the `private-cloud` boot entry instead.
- [ ] Disable the one-time boot menu.
- [ ] Enable Intel PTT.
- [ ] Enable VT-d and pre-boot DMA protection if offered.
- [ ] Enable Total Memory Encryption if offered.
- [ ] Set the host to power on after AC loss.

### Secure Boot owner keys

- [ ] Install openssl, efitools, and sbsigntool on the workstation.
- [ ] Run `python3 boot-integrity/workstation.py keys <directory>` on the workstation.
- [ ] Keep the private keys on the workstation only.
- [ ] Put the firmware in Setup Mode.
- [ ] Enroll `db.auth`, `KEK.auth`, then `PK.auth` through the firmware menu or `efi-updatevar`.
- [ ] Keep the existing keys until the signed UKI has booted once.

### Enable the stage

- [ ] Enable `boot_integrity` and set its interface, host address, and gateway in the installer.
- [ ] Confirm `/etc/crypttab` lists exactly one LUKS volume with the key field set to `none`.
- [ ] Run the installer and expect the final validation to fail until enrollment is complete.
- [ ] Copy `/var/lib/private-cloud/uki/<build>/unsigned.efi` to the workstation.
- [ ] Run `python3 boot-integrity/workstation.py sign unsigned.efi signed.efi <directory>`.
- [ ] Copy `signed.efi` to `/var/lib/private-cloud/uki/<build>/signed.efi` on the host.
- [ ] Rerun the installer to place the UKI on the ESP and create the `private-cloud` boot entry.
- [ ] Reboot and confirm the firmware boots the `private-cloud` entry with Secure Boot on.
- [ ] Remove the Microsoft keys only after the first signed boot succeeds.

### Enroll the unlock

- [ ] Unplug every external USB device, including the keyboard, except a USB system disk.
- [ ] Confirm the host booted the signed UKI.
- [ ] Rerun the installer and review the gateway MAC and USB device list.
- [ ] Enter the LUKS recovery passphrase when prompted.
- [ ] Reboot and confirm the host unlocks without input.
- [ ] Run the installer `validate` action.

### Board checks

- [ ] Record PCR 1 and PCR 5 across three cold boots and set `extra_pcrs` only if they stay identical.
- [ ] List the USB devices that `usbcore.authorized_default=2` leaves unauthorized.
- [ ] Confirm the PTT NV contents survive a cold boot and a power loss.
- [ ] Confirm the display works after the Microsoft UEFI CA is removed.
- [ ] Add drivers to `extra_drivers` if enrollment reports an initrd hardware difference.

### Maintenance visits

- [ ] Install held kernel, firmware, and boot-chain updates only while at the host.
- [ ] Follow the boot-integrity update procedure in [OPERATIONS.md](OPERATIONS.md#boot-integrity-updates).
- [ ] Confirm an unattended unlock after re-enrollment.

## External prerequisites

- [ ] Point the domain's authoritative DNS to Cloudflare before deployment.
- [ ] Use a registered domain, a reachable AirVPN WireGuard endpoint, and a public SMTP relay; validation rejects private or reserved substitutes.
- [ ] Create separate zone-scoped Cloudflare tokens for DDNS, Traefik ACME, and Stalwart ACME.
- [ ] Reserve `private_cloud.networking.lan.address` for the host on the router.
- [ ] Provide a physical Intel iGPU or supported PCI passthrough before enabling Intel GPU workloads.
- [ ] Select Immich CPU acceleration and disable the Intel GPU stage on VMware Workstation.
- [ ] Confirm the ISP provides a reachable public IPv4 address.
- [ ] Forward WAN TCP 443 and the configured AmneziaWG UDP port to the host.
- [ ] Point the router's DNS server, or the DNS it hands out over DHCP, at `private_cloud.networking.lan.address`.
- [ ] Configure no public secondary DNS on the router, because routers mix answers from both upstreams.
- [ ] Disable DNS rebind protection on the router so private answers for the domain pass through.
- [ ] Disable manually configured DNS-over-HTTPS or DNS-over-TLS on LAN devices.
- [ ] Keep the primary domain's `mail` and webmail records with the external inbox provider.

## Mail DNS and inbox

- [ ] Keep the primary domain's MX records pointed at the external inbox provider.
- [ ] Use the same provider account for the relay and the IMAP follower; it reads INBOX at `relay_host` TCP 993.
- [ ] Leave provider forwarding disabled; the follower copies new INBOX mail into Stalwart.
- [ ] Publish the SPF, DKIM, and DMARC records required by the external inbox and outbound relay.
- [ ] Publish and verify the DKIM record configured in Stalwart.
- [ ] Send a message to the provider address and confirm it arrives in Stalwart with the original sender's SPF result.
- [ ] Send a message through the external inbox and confirm it reaches the Stalwart mailbox.
- [ ] Verify outbound mail uses the configured inbox.eu relay and passes recipient-side authentication checks.

## AirVPN WireGuard values

- [ ] Open AirVPN Client Area, then Config Generator.
- [ ] Select Linux and WireGuard on UDP port 1637 or 47107, then generate a configuration for a server in the chosen country.
- [ ] Enter the chosen AirVPN countries as `media.vpn.server_countries`.
- [ ] Copy the `Endpoint` port to `media.vpn.endpoint_port`.
- [ ] Copy the `[Peer]` `PublicKey` to `media.vpn.peer_public_key`.
- [ ] Copy the `[Interface]` `Address` IPv4 value to `media.vpn.address`.
- [ ] Copy the `[Interface]` `MTU` to `media.vpn.mtu`.
- [ ] Copy the `[Interface]` `DNS` IPv4 value to `media.vpn.dns`.
- [ ] Copy the `[Peer]` `PersistentKeepalive` to `media.vpn.persistent_keepalive`.
- [ ] Enter the `[Interface]` `PrivateKey` as `media.wireguard_private_key` when prompted.
- [ ] Enter the `[Peer]` `PresharedKey` as `media.wireguard_preshared_key` when prompted.
- [ ] Ignore the endpoint hostname and IPv6 values; gluetun picks the server address from its built-in AirVPN list.

## Monitoring

- [ ] Configure external outage monitoring independent of this host and Stalwart.

- [ ] Review the live alert validation email and confirm it reaches the configured Stalwart mailbox.
- [ ] Expect a Traefik "no such file or directory" error alert after installer runs that change routes; Traefik reloads the routes and needs no action.

## Services

- [ ] Select Prowlarr indexers and provide their credentials.
- [ ] Reach the unpublished Prowlarr UI through `sudo k0s kubectl port-forward -n media service/prowlarr 9696:9696`.
- [ ] Select the `private-cloud` profile when adding Sonarr series, Radarr movies, or import lists.
- [ ] Add media libraries and confirm playback, scanning, and metadata downloads in Jellyfin.

## Identity

- [ ] Sign in to OpenCloud, Grist, AFFiNE, and Immich with the managed Stalwart mailbox account and its stored password.
- [ ] Confirm that account is the administrator in OpenCloud, Grist, AFFiNE, and Immich.
- [ ] Create a Stalwart account for each person at `https://<stalwart-hostname>/admin/`.
- [ ] Confirm a new account can sign in to OpenCloud, Grist, AFFiNE, and Immich.
- [ ] Assign application permissions and administrator grants within each application.
- [ ] Use Grist only from a browser session because API keys are unsupported.
- [ ] Note the ten-seat limit for the self-hosted AFFiNE workspace.

### Jellyfin native login

- [ ] Confirm the installer completed Jellyfin's initial setup.
- [ ] Create users and grant their library access in Jellyfin.
- [ ] Authorize supported native clients through Jellyfin Quick Connect.

## AmneziaWG peers

- [ ] Leave `vpn-admin.<domain>` out of public DNS; LAN DNS answers it.
- [ ] Sign in at `https://vpn-admin.<domain>` with `networking.amneziawg.admin_username` and the stored password.
- [ ] Enable two-factor authentication for the administrator in the UI.
- [ ] Create one client per device and scan its QR code with the AmneziaWG app.
- [ ] Enable the per-client firewall in the UI and set firewall entries to narrow single peers.
- [ ] Manage peers remotely only after connecting through the VPN.

## First administrators

- [ ] Sign in to Jellyfin with `private_cloud.media.jellyfin_admin_username` and the stored Jellyfin administrator password.
- [ ] Keep the stored Immich and AFFiNE administrator passwords for their local login forms.
- [ ] Record any generated password printed once by the installer.
- [ ] Change the passwords inside each application if desired.

## Network and DNS

- [ ] Test public access to configured HTTPS services, SMTP, and AmneziaWG from outside the LAN.
- [ ] Test LAN DNS from LAN and VPN clients.
- [ ] Confirm SSH, the Kubernetes API, and Zabbix are unavailable from WAN networks.
- [ ] Confirm the DKIM record resolves publicly.
- [ ] Verify the IMAP follower preserves the original sender address in Stalwart.
- [ ] Interrupt the AirVPN WireGuard tunnel and confirm guarded media apps lose external access.
- [ ] Confirm each AmneziaWG peer can reach only its approved LAN destinations.
- [ ] Confirm the AmneziaWG UI is unreachable from WAN.

## Deployment acceptance

Repository implementation is not evidence of live enforcement. Before exposure:

- [ ] Confirm the router forwards only TCP `443` and the AmneziaWG UDP port.
- [ ] Verify all other host and former NodePort paths fail from WAN and LAN.
- [ ] Verify SSH, Kubernetes API, and Zabbix work only from configured local networks.
- [ ] Test every hostname from WAN, LAN, and AmneziaWG.
- [ ] Verify LAN clients resolve service hostnames to the host address and pods to the Traefik Service.
- [ ] Verify Firefox and Apple devices on the LAN fall back to the LAN resolver.
- [ ] Verify OpenCloud, Grist, AFFiNE, and Immich complete a Stalwart OIDC login.
- [ ] Verify Grist login, the `/oauth2/callback` exchange, and logout through oauth2-proxy.
- [ ] Verify Grist rejects forged `X-Forwarded-User` headers from clients.
- [ ] Validate Traefik and Stalwart certificate issuance and renewal paths against the real Let's Encrypt service.
- [ ] Confirm Immich, AFFiNE, and Jellyfin answer with the installer-claimed administrators once published.
- [ ] Send a message to the external inbox and confirm the IMAP follower delivers it to Stalwart.
- [ ] Confirm Proxy Protocol preserves the sender address in Stalwart.
- [ ] Verify Stalwart filtering and outbound relay behavior.
- [ ] Interrupt the AirVPN WireGuard tunnel and confirm guarded apps lose Internet and external DNS.
- [ ] Confirm Immich machine learning downloads models over TCP `443`.
- [ ] Confirm Jellyfin downloads metadata over IPv4 and cannot initiate IPv6 connections.
- [ ] Confirm Jellyfin streaming and local scanning continue during media VPN failure.
- [ ] Verify the AmneziaWG LAN ceiling, per-peer UI firewall entries, and full-tunnel Internet egress.
- [ ] Verify the AmneziaWG UI rejects clients outside local networks and the VPN.
- [ ] Verify AmneziaWG peers cannot reach the pod or service CIDRs.
- [ ] Confirm qBittorrent reports `tun0` as its bound interface.
- [ ] Verify Jellyfin transcoding uses the Intel GPU.
- [ ] Confirm OpenObserve is reachable only through its configured hostname.
- [ ] Confirm Alloy has no public route and accepts only its documented internal health path.
- [ ] Run the installer `validate` action after operator setup is finished.

## Live validation

Validation runs only against the production services, public providers, and DNS configured for this host. It has no mocks, test CAs, endpoint overrides, or temporary policy openings.

```sh
sudo python3 ansible/install.py
```

Installation runs validation automatically after all enabled stages finish. Choose `validate` at the mode prompt to rerun it; it needs the stored public configuration, the encrypted secrets file, and the Vault password.

Complete the external prerequisites above before the first installation, or the final validation fails on the missing external state.

### Checked automatically

- ZFS health, encryption, mounts, quotas, and k0s startup ordering.
- Boot integrity: Secure Boot, signed UKI, armed TPM unlock, unattended unlock on the last boot, tripwire, console policy, and update holds.
- Cluster node, volume, and workload readiness.
- Service protocols, authenticated APIs, and OpenCloud storage round trips.
- HTTPS certificates chain to Mozilla public roots and expire in more than 14 days.
- Host DNS resolves every checked hostname to the host address in `networking.lan.address`.
- LAN DNS answers service hostnames with the host address and encrypted DNS canaries with NXDOMAIN.
- Cluster DNS answers service hostnames with the Traefik Service address.
- Cloudflare `1.1.1.1` and Google `8.8.8.8` resolve each managed record to the address returned by `networking.public_ip_url`.
- The IMAP follower checked the provider INBOX within the last 15 minutes.
- The primary-domain MX points away from Stalwart.
- The primary domain publishes SPF and DMARC records.
- Traefik, Stalwart, and DDNS use the production Let's Encrypt and Cloudflare endpoints.
- Stalwart uses the external SMTP relay for non-local outbound mail.
- Guarded media traffic exits through the VPN with an address different from the home WAN address.
- OpenCloud discovery and every enabled client callback are accepted.
- Internal SMTP validation, OpenObserve alerts, and Zabbix alerts reach the Stalwart mailbox.
- The host trust store contains no local CAs.
- `/etc/hosts` contains no service, relay, ACME, or Cloudflare overrides.
- Cluster CoreDNS has no static host overrides.
- Workloads have no `hostAliases`, CA environment overrides, or trust-store mounts.
- Every NetworkPolicy in managed namespaces comes from the repository templates.
- Managed namespaces contain no TLS Secrets and Traefik loads no injected certificates.

### Not checked automatically

- [ ] Confirm the router forwards only TCP 443 and the AmneziaWG UDP port from a separate WAN connection.
- [ ] Confirm SSH, the Kubernetes API, Zabbix, and former NodePorts are unreachable from WAN.
- [ ] Confirm LAN DNS from LAN clients other than the host and from AmneziaWG clients.
- [ ] Publish and verify the DKIM selector, because its name is provider-specific.
- [ ] Confirm the external inbox forwards real messages to the forwarding address.
- [ ] Confirm outbound mail passes SPF, DKIM, and DMARC at an external recipient.
- [ ] Confirm the Cloudflare tokens are zone-scoped with only DNS edit permission.
- [ ] Watch the first Let's Encrypt renewal for Traefik and Stalwart.
- [ ] Interrupt the AirVPN WireGuard tunnel and confirm guarded media apps lose Internet access.
- [ ] Connect an AmneziaWG peer from a separate client and check its LAN allowlist.
- [ ] Complete real browser and mobile sign-ins for every OIDC application.
- [ ] Confirm Intel GPU inference and transcoding on the installed hardware.
- [ ] Size memory and dataset quotas for actual documents, media, logs, and concurrency.
