# Bleve storage

The Bleve storage is managed by `ansible/roles/bleve`.

- Configure `private_cloud.bleve` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/bleve`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- Bleve is embedded in OpenCloud and does not run as a standalone service.
- OpenCloud mounts the Bleve claim for its search index.
