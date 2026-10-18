# Networking services

The networking services are managed by `ansible/roles/networking`.

- Traefik binds host TCP `443` for HTTPS and TCP `25` for SMTP.
- Application route ConfigMaps in `edge` use exact configured hostnames.
- Traefik reads routes only through the Grist route ConfigMap.
- Traefik uses Cloudflare DNS-01 for web certificates with explicit public resolvers.
- Traefik has no Kubernetes API access, RBAC, or service-account token.
- The `forward-auth` Deployment in `edge` runs oauth2-proxy for Grist.
- Traefik routes `/oauth2/` on the Grist host to oauth2-proxy through the file provider.
- Pods reach the public hostname through the Traefik pod port.
- The Cloudflare DDNS CronJob maintains configured public A records, proxy status, and TTL.
- AmneziaWG binds one configured UDP hostPort.
- AmneziaWG runs the userspace amneziawg-go implementation without a host kernel module.
- AmneziaWG routes and firewall rules remain inside its pod network namespace.
- Default-deny policies cover every managed namespace.
- The host nftables policy limits all other incoming ports.
- The Traefik dataset has a quota and a dedicated `10Ti` PV.

The home router and split-DNS server remain operator-managed.
