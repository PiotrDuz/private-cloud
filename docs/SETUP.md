# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## Host installation

- [ ] Install Ubuntu 26.04 LTS with "Use LVM and encryption" on the system disk.
- [ ] Do not select hardware-backed TPM encryption; the TPM design is in [TPM_ANALYSIS.md](TPM_ANALYSIS.md).
- [ ] Use a long random LUKS passphrase and store it offline as the recovery passphrase.
- [ ] Keep the `tank` pool disks out of the installer's partitioning.
- [ ] Give the Ubuntu administrator account a long random password; the console accepts it only after a TPM wipe.

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
- [ ] Reserve `private_cloud.networking.traefik_internal_ip` for the host on the router.
- [ ] Provide a physical Intel iGPU or supported PCI passthrough before enabling Intel GPU workloads.
- [ ] Select Immich CPU acceleration and disable the Intel GPU stage on VMware Workstation.
- [ ] Confirm the ISP provides a reachable public IPv4 address and permits inbound TCP 25.
- [ ] Ask the ISP to publish the reverse-DNS PTR record for the public mail address.
- [ ] Forward WAN TCP 25 and TCP 443, plus the configured AmneziaWG UDP port, to the host.
- [ ] Configure LAN and VPN split DNS for the configured service hostnames.
- [ ] Resolve the OpenCloud hostname to the Traefik address for LAN clients and pods.
- [ ] Keep public mail hostname records DNS-only so SMTP reaches the host directly.

## Mail DNS and forwarding

- [ ] Keep the primary domain's MX records pointed at the external inbox provider.
- [ ] Point the forwarding domain's MX record at the configured Stalwart mail hostname.
- [ ] Configure the external inbox to forward accepted messages to `<mailbox_username>@<forwarding_domain>`.
- [ ] Publish the SPF, DKIM, and DMARC records required by the external inbox and outbound relay.
- [ ] Publish and verify the DKIM record configured in Stalwart.
- [ ] Confirm the forwarding alias delivers mail to `<mailbox_username>@<domain>`.
- [ ] Send a message through the external inbox and confirm it reaches the Stalwart mailbox.
- [ ] Verify outbound mail uses the configured inbox.eu relay and passes recipient-side authentication checks.

## AirVPN WireGuard values

- [ ] Open AirVPN Client Area, then Config Generator.
- [ ] Select Linux and WireGuard, then choose one server.
- [ ] Copy the `Endpoint` IP address to `media.vpn.endpoint_ip` and its port to `media.vpn.endpoint_port`.
- [ ] Copy the `[Peer]` `PublicKey` to `media.vpn.peer_public_key`.
- [ ] Copy the `[Interface]` `Address` IPv4 value to `media.vpn.address`.
- [ ] Enter the `[Interface]` `PrivateKey` as `media.wireguard_private_key` when prompted.
- [ ] Enter the `[Peer]` `PresharedKey` as `media.wireguard_preshared_key` when prompted.
- [ ] Ignore the IPv6 address and `DNS`; the gateway uses the in-tunnel resolver `10.128.0.1`.
- [ ] Use a literal IP endpoint, not a hostname.

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

- [ ] Sign in to OpenCloud with the initialized administrator account.
- [ ] Manage users, passwords, account status, and groups through the OpenCloud admin area.
- [ ] Assign each user a unique administrator-controlled email address.
- [ ] Keep local administrator access in downstream applications.
- [ ] Assign application permissions and administrator grants within each application.
- [ ] Confirm newly enabled users can sign into Grist, AFFiNE, and Immich.
- [ ] Use Grist only from a browser session because API keys are unsupported.

### AFFiNE OIDC

- [ ] In the AFFiNE administration panel, add a generic OAuth2/OIDC provider.
- [ ] Set the issuer URL to `https://<opencloud-hostname>`.
- [ ] Set the client id to `affine` and the secret to `private_cloud_secrets.affine.oidc_client_secret`.
- [ ] Allow the redirect URI `https://<affine-hostname>/oauth/callback`.
- [ ] Set claims to `sub`, `email`, and `name` with scope `openid profile email`.
- [ ] Set `claim_email_verified` to `opencloud_admin_controlled_email` in the OIDC provider arguments.
- [ ] Enable `oauth.providers.oidc.allowPrivateNetwork` for the configured OpenCloud issuer.
- [ ] Note the ten-seat limit for the self-hosted AFFiNE workspace.

### Jellyfin native login

- [ ] Confirm the installer completed Jellyfin's initial setup.
- [ ] Create users and grant their library access in Jellyfin.
- [ ] Authorize supported native clients through Jellyfin Quick Connect.

## First administrators

- [ ] Sign in to Immich with `private_cloud.immich.admin_email` and the stored Immich administrator password.
- [ ] Sign in to AFFiNE with `private_cloud.affine.admin_email` and the stored AFFiNE administrator password.
- [ ] Sign in to Jellyfin with `private_cloud.media.jellyfin_admin_username` and the stored Jellyfin administrator password.
- [ ] Record any generated password printed once by the installer.
- [ ] Change the passwords inside each application if desired.

## Network and DNS

- [ ] Test public access to configured HTTPS services, SMTP, and AmneziaWG from outside the LAN.
- [ ] Test split DNS from LAN and VPN clients.
- [ ] Confirm SSH, the Kubernetes API, and Zabbix are unavailable from WAN networks.
- [ ] Confirm the DKIM record resolves publicly.
- [ ] Verify inbound SMTP preserves the sender address through Proxy Protocol.
- [ ] Interrupt the AirVPN WireGuard tunnel and confirm guarded media apps lose external access.
- [ ] Confirm each AmneziaWG peer can reach only its approved LAN destinations.

## Deployment acceptance

- [ ] Complete the deployment acceptance checklist in [NETWORKING.md](NETWORKING.md#deployment-acceptance).
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
- HTTPS and SMTP STARTTLS certificates chain to Mozilla public roots and expire in more than 14 days.
- Host split DNS resolves every checked hostname to `networking.traefik_internal_ip`.
- Cloudflare `1.1.1.1` and Google `8.8.8.8` resolve each managed record to the address returned by `networking.public_ip_url`.
- The forwarding-domain MX includes the Stalwart hostname.
- The primary-domain MX points away from Stalwart.
- The primary domain publishes SPF and DMARC records.
- The public address PTR equals the Stalwart hostname.
- Traefik, Stalwart, and DDNS use the production Let's Encrypt and Cloudflare endpoints.
- Stalwart uses the external SMTP relay for non-local outbound mail.
- Guarded media traffic exits through the VPN with an address different from the home WAN address.
- The WireGuard endpoint is a public IPv4 address.
- OpenCloud discovery and every enabled client callback are accepted.
- Internal SMTP validation, OpenObserve alerts, and Zabbix alerts reach the Stalwart mailbox.
- The host trust store contains no local CAs.
- `/etc/hosts` contains no service, relay, ACME, or Cloudflare overrides.
- Cluster CoreDNS has no static host overrides.
- Workloads have no `hostAliases`, CA environment overrides, or trust-store mounts.
- Every NetworkPolicy in managed namespaces comes from the repository templates.
- Managed namespaces contain no TLS Secrets and Traefik loads no injected certificates.

### Not checked automatically

- [ ] Confirm the router forwards only TCP 25, TCP 443, and the AmneziaWG UDP port from a separate WAN connection.
- [ ] Confirm SSH, the Kubernetes API, Zabbix, and former NodePorts are unreachable from WAN.
- [ ] Confirm the ISP permits inbound and outbound TCP 25.
- [ ] Confirm split DNS from LAN clients other than the host and from AmneziaWG clients.
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
