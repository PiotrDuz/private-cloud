# Networking services

The networking services are managed by `ansible/roles/networking`.

- Traefik binds host TCP `443` for HTTPS and TCP `25` for SMTP.
- Application Ingress resources use exact configured hostnames.
- Traefik uses Cloudflare DNS-01 for web certificates.
- The Cloudflare DDNS CronJob maintains configured public A records.
- AmneziaWG binds one configured UDP hostPort.
- The AmneziaWG kernel module is installed on the host.
- AmneziaWG routes and firewall rules remain inside its pod network namespace.
- Default-deny policies cover every managed namespace.
- The host nftables policy limits all other incoming ports.
- The Traefik dataset has a quota and a dedicated `10Ti` PV.

The home router and split-DNS server remain operator-managed.
