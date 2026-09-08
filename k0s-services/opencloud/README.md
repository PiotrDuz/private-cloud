# OpenCloud service

The OpenCloud service is managed by `ansible/roles/opencloud`.

- Ansible renders the `templates/*.yaml.j2` workload files during deployment.

- Configure `private_cloud.opencloud` in the public configuration.
- Store the administrator password in the encrypted configuration.
- Change the initialized administrator password through OpenCloud UI or CLI.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/opencloud`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The separately provisioned `bleve-data` PVC stores the search index.
- The OpenCloud PV stores generated configuration, files, and web extensions.
- Apache Tika provides full-text content extraction.
- OnlyOffice uses the embedded OpenCloud collaboration service.
- Both public hostnames must resolve from the pods with trusted certificate chains.
- WOPI proof checks are disabled for current OnlyOffice compatibility.
- The app registry maps supported office formats to OnlyOffice.
- The official Draw.io extension embeds `https://embed.diagrams.net`.
- The first Draw.io installation requires outbound access to its pinned GitHub release.
- ConfigMap changes trigger a Deployment rollout through rendered checksums.
- General caches use memory while the POSIX ID cache uses embedded NATS.
- A ClusterIP service exposes TCP `9200` only inside the cluster.
- Traefik publishes the configured hostname, including `/wopi` and `/collaboration`, through HTTPS.
