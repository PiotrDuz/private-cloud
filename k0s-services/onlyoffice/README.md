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
- The service exposes WOPI discovery inside the cluster and through a NodePort.
- Forward the OnlyOffice hostname to the configured NodePort through the TLS proxy.
- Preserve WebSockets and set `X-Forwarded-Proto` to `https` in the TLS proxy.
- Both public hostnames must be reachable from the pods with trusted certificates.
