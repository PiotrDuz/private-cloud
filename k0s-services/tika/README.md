# Apache Tika service

The Apache Tika service is managed by `ansible/roles/tika`.

- Configure `private_cloud.tika` in the public configuration.
- Run `sudo python3 ansible/install.py` from the repository root.
- The Kustomize base is the authoritative Kubernetes workload definition.
- Ansible patches the dataset path, storage node, image, and memory before applying it.
- Render the public example with `python3 ansible/render_manifests.py tika --base k0s-services/tika/kustomize/base --values k0s-services/tika/site-values.example.yaml`.
- The service dataset is `tank/secure/backup/k0s/services/tika`.
- The dataset uses the configured quota.
- The local PV and PVC advertise a fixed `10Ti` capacity.
- The service is reachable only inside the cluster on port `9998`.
- The persistent volume is mounted at `/var/lib/tika`.
- Tika is stateless and the PV follows the repository service-storage policy.
