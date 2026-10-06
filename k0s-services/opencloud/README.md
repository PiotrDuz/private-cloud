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
- The OpenCloud and OnlyOffice hostnames must resolve from the pods with trusted certificate chains.
- WOPI proof checks are disabled for current OnlyOffice compatibility.
- The app registry maps supported office formats to OnlyOffice.
- The official Draw.io extension embeds `https://embed.diagrams.net`.
- The first Draw.io installation requires outbound access to its pinned GitHub release.
- ConfigMap changes trigger a Deployment rollout through rendered checksums.
- The POSIX user storage driver requires the built-in NATS JetStream key-value cache for file IDs.
- A ClusterIP service exposes TCP `9200` only inside the cluster.
- Traefik publishes the configured hostname, including `/wopi` and `/collaboration`, through HTTPS.
- The collaboration service shares the OnlyOffice `JWT_SECRET` from `onlyoffice-credentials`.
- An OnlyOffice JWT secret rotation triggers an OpenCloud rollout through a rendered checksum.

## Shared identity

- OpenCloud runs its [built-in OIDC provider](https://docs.opencloud.eu/docs/dev/server/services/idp/information/) and directory.
- The issuer is `https://<opencloud-hostname>`.
- Public clients are `web`, `OpenCloudDesktop`, `OpenCloudAndroid`, and `OpenCloudIOS`.
- Enabled applications register confidential clients `grist-forward-auth`, `affine`, and `immich`.
- The role renders clients into the `opencloud-identity` Kubernetes Secret.
- The init container copies `idp.yaml` into the backed-up configuration directory with mode `0600`.
- Client configuration changes trigger an OpenCloud rollout.
- Generated signing keys and directory data stay on the OpenCloud dataset.
- Manage users, passwords, account status, groups, and roles through the OpenCloud admin area.
- Assign unique administrator-controlled email addresses before downstream sign-in.
- Every enabled user can sign into connected applications without a separate login allowlist.
- Manage downstream permissions and administrator grants within each application.
- Restore identity data, signing keys, and configuration from the same recovery point.
