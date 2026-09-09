# OnlyOffice service

The OnlyOffice service is managed by `ansible/roles/onlyoffice`.

- Configure `private_cloud.onlyoffice` in the public configuration.
- Store the JWT secret in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/onlyoffice`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The PV retains OnlyOffice logs, certificates, file cache, and internal database.
- The Community Edition container includes its required internal dependencies.
- OnlyOffice runs as UID 0 inside a user namespace mapped to an unprivileged host UID.
- A ClusterIP service exposes WOPI discovery only inside the cluster.
- Traefik publishes the configured hostname through HTTPS.
- The Ingress preserves WebSockets and the external HTTPS scheme.
- Both public hostnames must be reachable from the pods with trusted certificates.

## Logging

OnlyOffice 9.4.0.1 uses its native entrypoint to tail file-only operational logs to container output. It receives no logging sidecar.

- `/var/log/onlyoffice` persists on the service dataset.
- Host logrotate checks files every 15 minutes.
- Rotation uses a 10MiB size limit and seven-day retention.
- Rotation is best effort while the container is writing files.

## Manifest review

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.
