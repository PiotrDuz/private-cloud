# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## External prerequisites

- [ ] Point the domain's authoritative DNS to Cloudflare before deployment.
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
- [ ] Confirm the configured public A records appear in Cloudflare after the DDNS stage runs.

## Mail DNS and forwarding

- [ ] Keep the primary domain's MX records pointed at the external inbox provider.
- [ ] Point the forwarding domain's MX record at the configured Stalwart mail hostname.
- [ ] Configure the external inbox to forward accepted messages to `<mailbox_username>@<forwarding_domain>`.
- [ ] Publish the SPF, DKIM, and DMARC records required by the external inbox and outbound relay.
- [ ] Publish and verify the DKIM record configured in Stalwart.
- [ ] Confirm the forwarding alias delivers mail to `<mailbox_username>@<domain>`.
- [ ] Send a message through the external inbox and confirm it reaches the Stalwart mailbox.
- [ ] Verify outbound mail uses the configured inbox.eu relay and passes recipient-side authentication checks.
- [ ] Confirm the outbound relay presents a certificate chaining to a public Mozilla-trusted CA, because OpenObserve uses compiled-in webpki roots.

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
- [ ] Confirm the forwarding-domain MX and mail hostname resolve to the expected destinations.
- [ ] Confirm PTR, SPF, DKIM, and DMARC records resolve publicly.
- [ ] Verify inbound SMTP preserves the sender address through Proxy Protocol.
- [ ] Interrupt OpenVPN and confirm guarded media apps lose external access.
- [ ] Confirm each AmneziaWG peer can reach only its approved LAN destinations.

## Deployment acceptance

- [ ] Complete the deployment acceptance checklist in [NETWORKING.md](NETWORKING.md#deployment-acceptance).
- [ ] Complete the repository's live validation after operator setup is finished.

## Live validation

Run the installed-system validation from the repository root after deployment and operator setup:

```sh
sudo python3 ansible/install.py
```

Installation runs the configured live validation automatically after all enabled stages finish.

Choose `validate` at the mode prompt and enter the Ansible Vault password. Validation requires the existing public configuration and encrypted secrets file, and it checks enabled stages. It checks ZFS health, mounts, quotas and k0s startup ordering; cluster node and volume readiness; workload rollouts; ARR user IDs and qBittorrent's tunnel binding; OpenCloud callback acceptance; DNS lookups, trusted HTTPS routes and SMTP STARTTLS; the active host firewall; Zabbix collectors; log heartbeat ingestion; and synthetic OpenObserve and Zabbix email delivery.

The validation action does not create Cloudflare credentials, configure the router, publish mail MX or TXT records, configure ISP mail routing, create user accounts, or set application UI options. The DDNS stage updates the configured public A records. Test WAN reachability, split DNS from LAN and VPN clients, real user sign-ins, Jellyfin password login, VPN isolation, and media playback manually using the acceptance checklist above.

## Ephemeral VM acceptance

Local mocks can exercise DNS routing, trusted HTTPS, ACME account registration and certificate signing, SMTP relay forwarding, and an OpenVPN tunnel using the configured test hostnames. They cannot establish domain ownership, ISP routing, external provider credentials, public mail reputation, or physical GPU access.

For an already configured local trial, restore the mock processes and cluster fixtures after a guest reboot:

```sh
sudo python3 ansible/validation/mocks/live_test.py restore
```

The harness preserves its private credentials, CA, and VPN profile under `/var/lib/private-cloud-live-test`; it discards stale process IDs after a reboot. The saved mock profile must match the encrypted media configuration. Reapply can replace the mock workload mounts and Traefik certificate configuration, so restore these fixtures before validating the local trial.

- [ ] Restore the production ACME directory and Cloudflare API URLs in global configuration.
- [ ] Repeat DNS-01 issuance and renewal against an owned Cloudflare zone.
- [ ] Confirm public DNS records from an independent resolver.
- [ ] Confirm inbound forwarding and outbound delivery with the real mail providers.
- [ ] Test NAT and firewall access from a separate WAN connection.
- [ ] Replace the local VPN endpoint with the provider profile and credentials.
- [ ] Test an AmneziaWG peer from a separate client.
- [ ] Confirm Intel GPU inference and transcoding on accessible hardware.
- [ ] Size memory and dataset quotas for actual documents, media, logs, and concurrency.

See [the VMware acceptance record](LIVE_TEST.md) for measured results and remaining checks.
