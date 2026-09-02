# Manticore service

The Manticore service is managed by `ansible/roles/manticore`.

- The Kustomize base is the authoritative Kubernetes workload definition.
- Render the public example with `python3 ansible/render_manifests.py manticore --base k0s-services/manticore/kustomize/base --values k0s-services/manticore/site-values.example.yaml`.
- Configure `private_cloud.manticore` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The service dataset is `tank/secure/backup/k0s/services/manticore`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster on HTTP port `9308`.
- AFFiNE uses Manticore as its full-text indexer.
- Back up the dataset before changing the pinned Manticore image.
- Review Manticore release notes before upgrades.
