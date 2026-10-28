# Live install test report

Host: Hardkernel i3-N305, Ubuntu 26.04.1, 29 GiB RAM. Pool: RAIDZ1 on sda, sdc, sdd. System disk sdb not used.

## Progress

| Step | Status |
| --- | --- |
| Config redesign (LAN DNS, mx-inbound, JMAP only, AirVPN by country) | Done |
| Offline validation of planned answers | Passed |
| Installer prompts (create) | Passed |
| Preflight | Passed (after fix 3) |
| ZFS, k0s | Done |
| Networking | Done after fix 4 (rerun with `reapply`) |
| LAN DNS live check | `cloud.<domain>` → <LAN IP>, public names via DoT, canary NXDOMAIN |
| Intel GPU, PostgreSQL, Meilisearch | Done |
| Media (AirVPN tunnel + peer key check) | Done |
| Stalwart, Tika, Bleve, OnlyOffice, OpenCloud | Done |
| Let's Encrypt certs (cloud, onlyoffice, jellyfin, mx-inbound, vpn-admin) | Issued |
| Grist (forward-auth recovered) | Done |
| Manticore, Redis for AFFiNE, AFFiNE, Immich | Done |
| Logging | Done after fix 7 (rerun with `reapply`) |
| Zabbix server | Done |
| Zabbix agent | Failed: Stalwart SMTP certificate probe (issue 8) |
| Stalwart certificate | Issued 10:11 after lock expiry |
| Reapply with fixes 8–10 | Stalwart passed: one Stdout tracer, certificate step ok |
| Zabbix agent, notifications (rerun) | Done — main playbook complete |
| Main playbook (all stages) | Done |
| Validation: cluster, identity (incl. Immich) | Passed |
| Router DNS (ASUS AX55) | WAN DNS = <LAN IP> only; service names and 4 canaries consistent via router |
| Validation: split DNS, public DNS, mail records, observability, internal SMTP | Passed |
| Validation: Zabbix problem/recovery mail | Passed after fixes 16–18 |
| **Final `reapply` (2026-10-28)** | **Install ok=1324 failed=0; validation ok=282 failed=0** |

## Open items

- Delete in Cloudflare: 2× CAA on `mx-inbound.<domain>`, TXT `_validation-persist.mx-inbound.<domain>`.
- Test real inbound mail: inbox.eu forward → `<mailbox>@inbound.<domain>` (ISP port 25, spam/SRS handling).
- Changes are uncommitted.

## Issues and fixes

| # | Issue | Fix |
| --- | --- | --- |
| 1 | Driver did not know sudo prompt `[sudo: authenticate] Password:` | Driver answer added (driver only, not repo) |
| 2 | Driver mismatched prompts with trailing spaces | Driver normalises prompts (driver only) |
| 3 | Preflight "Validate logging and notification configuration" passed the resolved config to `validate_public_configuration`, which expects the stored form | `roles/preflight/tasks/main.yml` now calls `validate_resolved_configuration` |
| 4 | LAN DNS pod crashed: `exec /coredns: operation not permitted`; the CoreDNS binary carries a file capability blocked by `drop: [ALL]` | `lan-dns.yaml.j2` adds `NET_BIND_SERVICE`, as the media DNS does |
| 5 | forward-auth crash-looped (OIDC discovery of `cloud.<domain>` failed) | No fix; caused by fix 4 and OpenCloud not deployed yet |
| 6 | Traefik logged `jellyfin.yaml: no such file or directory` once | No fix; transient ConfigMap swap during reload, route serves correctly |
| 7 | Logging validation failed: `dict has no attribute 'value'`; Kubernetes drops `value: ""` from empty SMTP env vars | `roles/logging/validation/main.yml` uses `map(attribute='value', default='')` |
| 8 | Port 25 served a self-signed certificate. The role's final restart killed the first ACME task; Stalwart 0.16 keeps a 1-hour task lock in PostgreSQL, so no retry happened before validation | New `files/ensure_certificate.py` (+ `jmap_helpers.py`) runs after the final restart: if no certificate exists it creates a fresh `AcmeRenewal` task and waits up to 10 min |
| 9 | Stalwart logs were lost: default file tracer writes to missing `/var/log/stalwart` | Plan reconciles `Tracer` to one `Stdout` tracer |
| 10 | Stalwart published CAA `issue letsencrypt.org; accounturi=<Stalwart account>` on `mx-inbound.<domain>`, blocking Traefik's renewal for the same name | Plan publishes only `tlsa` (zone has no DNSSEC); existing CAA and `_validation-persist` records need manual removal; Stalwart now also publishes inert TLSA records |
| 11 | Validation "Require each enabled service claim to exist" looked for `amneziawg-data` in `private-cloud`; it lives in `network-access` | `validation/cluster.yml` maps `amneziawg` to `network-access` |
| 12 | Identity check rejected a correct OpenCloud sign-in redirect: `startswith("https://cloud.<domain>/")` matches every URL on the host | `validation/check_identity.py` compares the target without query to the redirect URI exactly |
| 13 | Identity check expected `invalid_client` for an unregistered redirect; OpenCloud answers client failures with `access_denied` (valid client still gets `invalid_grant`) | `check_identity.py` accepts `invalid_client` or `access_denied` |
| 14 | Immich OIDC client was never registered: OpenCloud (lico) skips a web client whose redirect is not HTTPS, and `app.immich:///oauth-callback` failed; Immich login via OpenCloud was broken | Register `https://photos.<domain>/api/oauth/mobile-redirect` and enable Immich's mobile redirect override (idp template, Immich deployment, validation, PLAN.md, README) |
| 15 | Router (ASUS AX55) mixed answers: with a public secondary WAN DNS, its resolver sometimes returned the public IP and public canary answers | Secondary removed; router forwards only to <LAN IP> (user change) |
| 16 | Zabbix rejected the validator's trapper value: host accepts PSK only, validator sent unencrypted | `validate_alert_delivery.py` sends over TLS-PSK with the agent identity and key |
| 17 | Recovery alerts were dropped by Stalwart as duplicates: `[Warning] X` and `[RESOLVED] X` share thread name and References | Recovery subject is now `Resolved: {EVENT.NAME}` (`zabbix/notification_helpers.py`) |
| 18 | Alerts were filed in Junk by the spam filter | Plan sets `MtaStageData.enableSpamFilter` to skip the alert port 2525 |

## Files

- Credentials, installer transcripts and generated passwords stay on the host, outside the repository.
