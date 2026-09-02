# Bleve storage

The Bleve storage is managed by `ansible/roles/bleve`.

- Configure `private_cloud.bleve` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/bleve`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- Bleve is embedded in OpenCloud and does not run as a standalone service.
- OpenCloud mounts the Bleve claim for its search index.

## Manifest review

- The Kustomize base is the authoritative public workload definition.
- Install Kustomize to render without root or a cluster.

```bash
python3 ansible/render_manifests.py bleve --base k0s-services/bleve/kustomize/base --values k0s-services/bleve/site-values.example.yaml
```
