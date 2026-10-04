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

## Authentication

- Stalwart uses the internal directory with native mailbox and administrator passwords.
- The `Authentication` singleton leaves `directoryId` null.
- Manage mailboxes, aliases, quotas, permissions, and app passwords in Stalwart.

## Mailbox lifecycle

- Stalwart 0.16 has no account-level enabled flag.
- Suspend, resume, and delete are operator actions through `stalwart-cli`.
- Run the commands against `https://<stalwart.hostname>`.
- Authenticate with native administrator credentials through `STALWART_USER` and `STALWART_PASSWORD`.
- List the account id with `stalwart-cli query Account --where name=<username>`.
- Suspend an account with `stalwart-cli update Account <id> --field 'permissions={"@type":"Merge","disabledPermissions":{"authenticate":true,"authenticateWithAlias":true}}'`.
- Resume an account with `stalwart-cli update Account <id> --field 'permissions={"@type":"Inherit"}'`.
- Delete an account with `stalwart-cli delete Account --ids <id>`.
- Suspension keeps the mailbox, aliases, and stored mail.
- Deletion removes the mailbox and its aliases.

## Filtering

- Stalwart enables the spam filter by default.
- The plan pins `SpamSettings` with `scoreSpam` `5`, `trustContacts`, and `trustReplies`.
- `scoreReject` and `scoreDiscard` stay `0`, so forwarded mail is never bounced or dropped.
- Users filter on the `X-Spam-Status` and `X-Spam-Result` headers.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
