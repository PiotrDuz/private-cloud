# Stalwart service

The Stalwart service is managed by `ansible/roles/stalwart`.

- The installer reads `private_cloud.stalwart` from the public configuration.
- The encrypted configuration holds database, mailbox, administrator, relay, and Cloudflare credentials.
- The dataset is `tank/secure/backup/k0s/services/stalwart`.
- The dataset has a quota and a dedicated `10Ti` PV.
- PostgreSQL stores metadata and the PV stores message blobs.
- Meilisearch stores the full-text search index.
- Stalwart uses a scoped Meilisearch key limited to `st_*` indexes, never the master key.
- The role creates the key with a fixed `uid` and stores it in `stalwart-runtime-credentials`.
- Non-local mail uses the configured inbox.eu SMTP relay.
- A ClusterIP service exposes HTTP/JMAP TCP `8080`.
- Notifications enable an internal SMTP listener on TCP `2525` for OpenObserve and Zabbix.
- Internal alerts use plain SMTP without authentication and cannot relay to external recipients.
- Traefik publishes JMAP, web access, and management through HTTPS TCP `443`.
- The HTTP listener reads the client address from `X-Forwarded-For` (`Http.useXForwarded`).
- Stalwart cannot limit forwarded headers by source, so a network policy limits TCP `8080` to Traefik and the configuration Job.
- The `strip-forwarded` Traefik middleware drops client-supplied `Forwarded` headers.
- Stalwart obtains and renews its certificate with Let's Encrypt DNS-01.
- DNS-01 propagation checks use the pod resolver, so no public port `53` egress is needed.
- The certificate workflow uses its dedicated Cloudflare DNS token.
- Automatic DNS publishes only TLSA, because Stalwart's CAA `accounturi` record would block Traefik's certificate for the same hostname.
- Submission ports `465` and `587` and IMAPS `993` are not published.

## Inbound mail

- The external inbox receives Internet mail; no inbound SMTP port is published.
- The `imap-fetch` sidecar follows the provider INBOX over IMAP IDLE with the relay credentials.
- It reads with `BODY.PEEK` and never flags, moves, or deletes provider mail.
- It starts after the newest message and keeps the last UID in `imap-fetch/state.json` on the dataset.
- It delivers each message to SMTP TCP `25` on loopback with Proxy Protocol v2.
- The Proxy Protocol header names the original client from the provider's own top `Received` headers.
- The SMTP listener trusts Proxy Protocol only from loopback.
- SPF, iprev, DKIM, DMARC, and the spam filter therefore evaluate the original sender.
- Stalwart drops a message delivered twice after a follower restart.
- The follower logs `start`, `delivered`, `rejected`, and `retry` events as JSON on stdout.

## Authentication

- Stalwart uses the internal directory with native mailbox and administrator passwords.
- The `Authentication` singleton leaves `directoryId` null.
- Mailboxes, aliases, quotas, permissions, and app passwords live in Stalwart.

## OIDC provider

- Stalwart is the OpenID Connect provider for OpenCloud, Grist, AFFiNE, and Immich.
- The issuer is `https://<stalwart-hostname>`.
- Every Stalwart account can sign in to every enabled application.
- The plan pins ES256 ID token signatures so applications verify them against the published JWKS.
- The plan upserts one `OAuthClient` per enabled application with its exact redirect URIs.
- OpenCloud registers public `web`, `OpenCloudDesktop`, `OpenCloudAndroid`, and `OpenCloudIOS` clients.
- Grist, AFFiNE, and Immich register confidential clients with secrets from the encrypted configuration.
- Loopback redirects match any port, so the desktop client works with its random callback port.
- Stalwart 0.16.26 rejects the desktop client's dynamic registration, which then falls back to its registered client ID.
- ID tokens carry `sub`, `preferred_username`, and `email`; userinfo adds `name` and `email_verified`.
- Access tokens are opaque, so OpenCloud validates them through the userinfo endpoint.
- A Traefik router adds CORS for `/auth/` so OpenCloud Web can exchange tokens from the browser.
- The plan upserts clients and never deletes clients added outside the installer.

## Logging

- The plan reconciles `Tracer` to a single `Stdout` tracer at `info`.
- The default file tracer is removed because `/var/log/stalwart` does not exist in the container.

## Mailbox lifecycle

- Stalwart 0.16 has no account-level enabled flag.
- Suspension removes the authentication permissions and keeps the mailbox, aliases, and stored mail.
- A suspended account cannot sign in to any application.
- Deletion removes the mailbox and its aliases.

## Filtering

- Stalwart enables the spam filter by default.
- The plan pins `SpamSettings` with `scoreSpam` `5`, `trustContacts`, and `trustReplies`.
- `scoreReject` and `scoreDiscard` stay `0`, so forwarded mail is never bounced or dropped.
- Users filter on the `X-Spam-Status` and `X-Spam-Result` headers.
- The internal alert listener skips the spam filter, so alerts never land in Junk.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
- Pods disable service links because the `stalwart` Service collides with `STALWART_*` variables.
