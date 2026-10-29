# OnlyOffice service

The OnlyOffice service is managed by `ansible/roles/onlyoffice`.

- The installer reads `private_cloud.onlyoffice` from the public configuration.
- The encrypted configuration holds the JWT secret.
- The OpenCloud WOPI signing secret is never mounted into OnlyOffice.
- The service dataset is `tank/secure/backup/k0s/services/onlyoffice`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV retains OnlyOffice logs, certificates, file cache, and internal database.
- The Community Edition container includes its required internal dependencies.
- OnlyOffice runs as UID 0 inside a user namespace mapped to an unprivileged host UID.
- A ClusterIP service exposes WOPI discovery only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The route ConfigMap preserves WebSockets and the external HTTPS scheme.
- Both public hostnames must be reachable from the pods with trusted certificates.
- The image is pinned by tag and digest.

## WOPI host restriction

- The `onlyoffice-config` ConfigMap mounts `local-production-linux.json` next to the generated `local.json`.
- It sets `services.CoAuthoring.ipfilter.rules` to allow only the OpenCloud hostname and deny `*`.
- Document Server applies the rules to every outgoing WOPI request, so a foreign `WOPISrc` receives HTTP 403.
- The validation posts a `WOPISrc` on the OnlyOffice hostname and requires `statusCode = "403"`.
- The OpenCloud validation posts a `WOPISrc` on the OpenCloud hostname and requires the OpenCloud `401`.
- Document Server signs WOPI requests with the proof key persisted in `/var/www/onlyoffice/Data`.
- OpenCloud verifies the proof headers against the discovery document.
- A rule change rolls the pod through the ConfigMap checksum annotation.

## Container privileges

- The container drops all capabilities and disables privilege escalation.
- `CHOWN`, `DAC_OVERRIDE`, and `FOWNER` cover the entrypoint's recursive ownership and mode changes.
- `SETUID` and `SETGID` let supervisord, nginx, cron, and `sudo -u postgres` switch users.
- `KILL` lets supervisord signal processes owned by `ds` and `postgres`.
- `NET_BIND_SERVICE` lets the nginx master bind port 80.
- `sudo` runs as root, so the no-new-privileges flag does not block it.

## Logging

OnlyOffice 9.4.0.1 uses its native entrypoint to tail file-only operational logs to container output. It receives no logging sidecar.

- `/var/log/onlyoffice` persists on the service dataset.
- Host logrotate checks files every 15 minutes.
- Rotation uses a 10MiB size limit and seven-day retention.
- Rotation is best effort while the container is writing files.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
