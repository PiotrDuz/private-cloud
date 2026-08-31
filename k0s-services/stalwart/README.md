# Stalwart service

The Stalwart service is managed by `ansible/roles/stalwart`.

- Configure `private_cloud.stalwart` in the public configuration.
- Store database, mailbox, administrator, and relay passwords in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/stalwart`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- PostgreSQL stores metadata and the PV stores message blobs.
- Meilisearch stores the full-text search index.
- The forwarding-domain alias delivers to the primary mailbox.
- Non-local mail uses the configured inbox.eu SMTP relay.
- Stalwart requests the hostname certificate with ACME TLS-ALPN-01.
- Gmail uses the primary mailbox address and mailbox password.
- Gmail IMAP uses the configured hostname on port `993` with SSL.
- Gmail SMTP uses the configured hostname on port `465` with SSL or `587` with STARTTLS.
- Forward public ports `443`, `25`, `465`, `587`, and `993` to their configured NodePorts.
- Public port `443` must reach Stalwart before certificate issuance.
