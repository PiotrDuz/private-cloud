# Stalwart service

The Stalwart service is managed by `ansible/roles/stalwart`.

- Configure `private_cloud.stalwart` in the public configuration.
- Store database, mailbox, administrator, relay, and Cloudflare credentials in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The dataset is `tank/secure/backup/k0s/services/stalwart`.
- The dataset has a quota and a dedicated `10Ti` PV.
- PostgreSQL stores metadata and the PV stores message blobs.
- Meilisearch stores the full-text search index.
- The forwarding-domain alias delivers to the primary mailbox.
- Non-local mail uses the configured inbox.eu SMTP relay.
- A ClusterIP service exposes HTTP/JMAP TCP `8080` and SMTP TCP `25`.
- Traefik publishes JMAP, web access, and management through HTTPS TCP `443`.
- Traefik proxies public SMTP TCP `25` with Proxy Protocol v2.
- Stalwart terminates SMTP STARTTLS itself.
- Stalwart obtains and renews its certificate with Let's Encrypt DNS-01.
- The certificate workflow uses its dedicated Cloudflare DNS token.
- Submission ports `465` and `587` and IMAPS `993` are not published.
- The external inbox receives Internet mail and forwards it to the Stalwart forwarding domain.
- Stalwart filtering controls which inbound forwarded messages are accepted.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
