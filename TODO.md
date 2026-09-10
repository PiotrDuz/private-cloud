# Outstanding work

[PLAN.md](PLAN.md) defines the target state; unchecked items here remain to be completed or verified.

Backup automation, snapshot retention, and recovery planning are deferred.

## Independent monitoring and startup acceptance

- [ ] Configure external outage monitoring independent of this host and Stalwart.
- [ ] Verify ZFS unlock, mount, and k0s startup ordering after reboot.

## Service and network operator setup

- [ ] Select Prowlarr indexers and provide their credentials.
- [ ] Choose Sonarr and Radarr quality profiles.
- [ ] Verify the provisioned ARR connections and library folders after deployment.
- [ ] Verify Jellyfin local library scans, playback, and disabled online integrations after deployment.
- [ ] Configure router forwarding for TCP 25, TCP 443, and the AmneziaWG UDP port.
- [ ] Configure public A records, forwarding-domain MX, and LAN/VPN split DNS.
- [ ] Publish and verify PTR, SPF, DKIM, and DMARC for the mail design.
- [ ] Verify Stalwart JMAP, forwarded inbound mail, recipient mapping, filtering, and outbound relay.
- [ ] Verify Traefik and Stalwart certificate issuance and renewal.
- [ ] Complete the deployment acceptance checklist in [NETWORKING.md](docs/NETWORKING.md#deployment-acceptance).

## Logging and notification acceptance

- [ ] Confirm timestamped logs from every enabled service and host source appear in OpenObserve.
- [ ] Review live unclassified logs for additional service formats requiring severity parsing.
- [ ] Confirm collection resumes after a collector restart and a bounded OpenObserve outage.
- [ ] Confirm source rotation and expired OpenObserve data deletion reclaim space.
- [ ] Verify an isolated log warning, log error, and Kubernetes Warning each generate email.
- [ ] Verify Zabbix Warning and higher problems generate email and recovery messages.
- [ ] Verify query failure, missing heartbeat, and SMTP failure remain visible as problems.
- [ ] Confirm actual messages arrive in the Stalwart inbox rather than only reaching the relay.
- [ ] Verify logging access does not weaken media VPN or Jellyfin isolation.
- [ ] Confirm the router, DNS, certificates, and media integrations in the live environment.
