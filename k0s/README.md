# k0s on the encrypted ZFS pool

This setup puts the k0s persistent data directory on `tank/secure/k0s`.
Containerd's image and writable-layer storage is kept in the separate
`tank/secure/k0s-containerd` dataset, mounted at `tank/secure/k0s/containerd`.
This preserves the path k0s expects while allowing containerd's high-churn,
re-creatable data to have separate snapshot, backup, and quota policies.
OpenZFS 2.4.1 supports the OverlayFS features used by containerd.

It also creates two ZFS datasets for native Kubernetes local PersistentVolumes:

- `tank/secure/k8s-volumes/pv01`
- `tank/secure/k8s-volumes/pv02`

Each dataset has a 5 GiB ZFS quota and matching reservation, but is advertised
to Kubernetes as a 100 TB (`100T`) PersistentVolume. The deliberately large
advertised capacity avoids Kubernetes PV/PVC expansion work. The ZFS dataset
quota remains the authoritative storage guard. The `local-zfs` StorageClass is
the cluster default.

## Install

Review the installer, then run:

```bash
sudo ./k0s/setup-k0s-zfs.sh
```

The default cluster is a combined controller and worker. It does not use
`--single`, so more controllers or workers can be added later.

The defaults can be overridden:

```bash
PV_COUNT=3 \
PV_SIZE_ZFS=20G \
PV_SIZE_K8S=100T \
K0S_VERSION=v1.36.2+k0s.0 \
sudo -E ./k0s/setup-k0s-zfs.sh
```

`PV_SIZE_ZFS` controls the actual quota and reservation of each dataset.
`PV_SIZE_K8S` controls only the capacity reported by each Kubernetes
PersistentVolume. Growing a volume within the advertised 100 TB therefore
requires changing the ZFS quota, without editing the PV or PVC.

Do not rerun the installer over an existing k0s service. It intentionally
refuses to replace an existing cluster.

## Use a volume

Apply the example claim:

```bash
sudo k0s kubectl apply -f k0s/pvc-example.yaml
sudo k0s kubectl get pvc,pv
```

Each static PersistentVolume can bind to one claim. Claims may request less
than the advertised 100 TB, but the unused advertised capacity of that PV
cannot satisfy a second claim. The example claim requests 5 GiB and binds to a
100 TB PV; the request does not reduce the ZFS quota or create an additional
filesystem limit.

Kubernetes does not know the dataset's real quota or remaining pool space. If a
workload reaches the ZFS quota, filesystem writes fail even though Kubernetes
still reports 100 TB of PV capacity. Monitor ZFS usage and raise
`PV_SIZE_ZFS` (or the dataset's `quota` property) before it fills.

## Native local-volume limitation

OverlayFS and PersistentVolumes solve different problems:

- OverlayFS lets containerd keep image layers and container writable layers in
  the ZFS-backed `tank/secure/k0s-containerd` dataset mounted inside the k0s
  data directory.
- Kubernetes' built-in `local` volume support lets a claim bind to a
  pre-created ZFS dataset without a CSI plugin.
- Native local volumes do not dynamically create a new ZFS dataset for each
  claim. Dynamic provisioning, Kubernetes-managed ZFS snapshots, and automatic
  dataset deletion require an external ZFS provisioner or CSI driver.

The PV reclaim policy is `Retain`, so deleting a claim does not erase its ZFS
dataset. Reusing a released PV requires an explicit administrator decision and
data cleanup.

## Boot behavior

The installer adds `k0s-zfs-mount.service`. It loads the key for `tank/secure`
from the configured `/etc/zfs/keys/tank-secure.key`, mounts its datasets, and
only then allows `k0scontroller.service` to start.

The existing key was originally created by `zfs-setup.sh` from a literal
password. Rotate that key before storing important data.
