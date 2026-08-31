# PostgreSQL service

The PostgreSQL service is managed by `ansible/roles/postgres`.

- Configure `private_cloud.postgres` in the public configuration.
- Store the administrator password in the encrypted configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/postgres`.
- The dataset quota and reservation use the configured volume size.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The container memory limit uses the configured maximum RAM.
- PostgreSQL `shared_buffers` uses half of the configured maximum RAM.
- The image remains `postgres:18.4-bookworm`.
