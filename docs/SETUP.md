# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## External prerequisites

- [ ] Point the domain's authoritative DNS to Cloudflare before deployment.
- [ ] Use a registered domain, a reachable OpenVPN provider endpoint, and a public SMTP relay; validation rejects private or reserved substitutes.
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

## Monitoring

- [ ] Configure external outage monitoring independent of this host and Stalwart.

- [ ] Review the live alert validation email and confirm it reaches the configured Stalwart mailbox.

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

- [ ] Complete Jellyfin's initial setup with a native administrator password.
- [ ] Create users and grant their library access in Jellyfin.
- [ ] Authorize supported native clients through Jellyfin Quick Connect.

## Network and DNS

- [ ] Test public access to configured HTTPS services, SMTP, and AmneziaWG from outside the LAN.
- [ ] Test split DNS from LAN and VPN clients.
- [ ] Confirm SSH, the Kubernetes API, and Zabbix are unavailable from WAN networks.
- [ ] Confirm the DKIM record resolves publicly.
- [ ] Verify inbound SMTP preserves the sender address through Proxy Protocol.
- [ ] Interrupt OpenVPN and confirm guarded media apps lose external access.
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
- The OpenVPN endpoint is a public IPv4 address.
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
- [ ] Interrupt OpenVPN and confirm guarded media apps lose Internet access.
- [ ] Connect an AmneziaWG peer from a separate client and check its LAN allowlist.
- [ ] Complete real browser and mobile sign-ins for every OIDC application.
- [ ] Confirm Intel GPU inference and transcoding on the installed hardware.
- [ ] Size memory and dataset quotas for actual documents, media, logs, and concurrency.
