# Operator setup

This runbook lists work that cannot be automated in this repository. Repository automation work is tracked in [TODO.md](../TODO.md); the deployed architecture is in [NETWORKING.md](NETWORKING.md) and [OPERATIONS.md](OPERATIONS.md).

## Monitoring

- [ ] Configure external outage monitoring independent of this host and Stalwart.

## Services

- [ ] Select Prowlarr indexers and provide their credentials.
- [ ] Select the `private-cloud` profile when adding Sonarr series, Radarr movies, or import lists.

## Network and DNS

- [ ] Configure router forwarding for TCP 25, TCP 443, and the AmneziaWG UDP port.
- [ ] Configure LAN and VPN split DNS.
- [ ] Request the PTR record for the mail design from the ISP.
- [ ] Send a message through the external inbox and confirm the forward reaches the Stalwart inbox.

## Deployment acceptance

- [ ] Complete the deployment acceptance checklist in [NETWORKING.md](NETWORKING.md#deployment-acceptance).
- [ ] Confirm the router, DNS, certificates, and media integrations in the live environment.
