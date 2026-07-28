#!/usr/bin/env bash
set -Eeuo pipefail

# Override these at invocation time if needed, for example:
#   PV_COUNT=3 PV_SIZE_ZFS=20G PV_SIZE_K8S=100T sudo -E ./k0s/setup-k0s-zfs.sh
ROOT_DATASET="${ROOT_DATASET:-tank/secure}"
K0S_VERSION="${K0S_VERSION:-v1.36.2+k0s.0}"
PV_COUNT="${PV_COUNT:-2}"
PV_SIZE_ZFS="${PV_SIZE_ZFS:-5G}"
# This is deliberately an advertised capacity, not the storage guard. The
# per-dataset ZFS quota above remains the authoritative write limit.
PV_SIZE_K8S="${PV_SIZE_K8S:-100T}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
K0S_DATASET="${ROOT_DATASET}/k0s"
CONTAINERD_DATASET="${ROOT_DATASET}/k0s-containerd"
VOLUMES_DATASET="${ROOT_DATASET}/k8s-volumes"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

dataset_exists() {
  zfs list -H -o name "$1" >/dev/null 2>&1
}

ensure_dataset() {
  local dataset="$1"
  local mountpoint="$2"

  if dataset_exists "$dataset"; then
    local current_mountpoint
    current_mountpoint="$(zfs get -H -o value mountpoint "$dataset")"
    [[ "$current_mountpoint" == "$mountpoint" ]] ||
      die "${dataset} exists with mountpoint ${current_mountpoint}, expected ${mountpoint}"
  else
    zfs create \
      -o mountpoint="$mountpoint" \
      -o compression=zstd \
      -o atime=off \
      -o xattr=sa \
      -o acltype=posixacl \
      "$dataset"
  fi

  zfs mount "$dataset" 2>/dev/null || [[ "$(zfs get -H -o value mounted "$dataset")" == "yes" ]]
}

if (( EUID != 0 )); then
  die "Run this installer as root: sudo $0"
fi

for command_name in curl grep install mountpoint sed seq systemctl zfs zpool; do
  require_command "$command_name"
done

[[ "$PV_COUNT" =~ ^[1-9][0-9]*$ ]] || die "PV_COUNT must be a positive integer"
dataset_exists "$ROOT_DATASET" || die "ZFS dataset ${ROOT_DATASET} does not exist"
zpool list "${ROOT_DATASET%%/*}" >/dev/null

root_mountpoint="$(zfs get -H -o value mountpoint "$ROOT_DATASET")"
[[ "$root_mountpoint" == /* ]] ||
  die "${ROOT_DATASET} needs an absolute mountpoint, found: ${root_mountpoint}"

if [[ "$(zfs get -H -o value keystatus "$ROOT_DATASET")" == "unavailable" ]]; then
  zfs load-key "$ROOT_DATASET"
fi
zfs mount "$ROOT_DATASET" 2>/dev/null || [[ "$(zfs get -H -o value mounted "$ROOT_DATASET")" == "yes" ]]

k0s_data_dir="${root_mountpoint}/k0s"
containerd_data_dir="${k0s_data_dir}/containerd"
volumes_root="${root_mountpoint}/k8s-volumes"

ensure_dataset "$K0S_DATASET" "$k0s_data_dir"
ensure_dataset "$CONTAINERD_DATASET" "$containerd_data_dir"
ensure_dataset "$VOLUMES_DATASET" "$volumes_root"

for ((index = 1; index <= PV_COUNT; index++)); do
  printf -v suffix '%02d' "$index"
  pv_dataset="${VOLUMES_DATASET}/pv${suffix}"
  pv_path="${volumes_root}/pv${suffix}"
  ensure_dataset "$pv_dataset" "$pv_path"
  zfs set quota="$PV_SIZE_ZFS" reservation="$PV_SIZE_ZFS" "$pv_dataset"
done

# The encrypted parent cannot be mounted by zfs-mount.service until its key is
# loaded. This helper and unit make that ordering explicit before k0s starts.
install -m 0755 "${SCRIPT_DIR}/k0s-zfs-mount.sh" /usr/local/sbin/k0s-zfs-mount
sed "s|@@ROOT_DATASET@@|${ROOT_DATASET}|g" \
  "${SCRIPT_DIR}/k0s-zfs-mount.service.in" \
  > /etc/systemd/system/k0s-zfs-mount.service
systemctl daemon-reload
systemctl enable --now k0s-zfs-mount.service

if ! command -v k0s >/dev/null 2>&1; then
  installer="$(mktemp)"
  trap 'rm -f -- "$installer"' EXIT
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error \
    https://get.k0s.sh -o "$installer"
  K0S_VERSION="$K0S_VERSION" sh "$installer"
fi

if systemctl list-unit-files k0scontroller.service --no-legend 2>/dev/null |
  grep -q '^k0scontroller\.service'; then
  die "k0scontroller.service already exists; refusing to overwrite an existing cluster"
fi

k0s install controller \
  --enable-worker \
  --no-taints \
  --data-dir="$k0s_data_dir"

install -d -m 0755 /etc/systemd/system/k0scontroller.service.d
install -m 0644 \
  "${SCRIPT_DIR}/k0scontroller-zfs.conf" \
  /etc/systemd/system/k0scontroller.service.d/zfs.conf
systemctl daemon-reload
k0s start

printf 'Waiting for the Kubernetes node to become Ready...\n'
node_name=""
node_ready=false
for _ in $(seq 1 60); do
  node_name="$(k0s kubectl get nodes -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "$node_name" ]] &&
    [[ "$(k0s kubectl get node "$node_name" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)" == "True" ]]; then
    node_ready=true
    break
  fi
  sleep 5
done
[[ "$node_ready" == "true" ]] || die "k0s started, but its node did not become Ready within five minutes"

storage_manifest="/etc/k0s/local-zfs-storage.yaml"
install -d -m 0755 /etc/k0s
install -m 0644 "${SCRIPT_DIR}/storage-class.yaml" "$storage_manifest"

for ((index = 1; index <= PV_COUNT; index++)); do
  printf -v suffix '%02d' "$index"
  {
    printf '%s\n' '---'
    sed \
      -e "s|@@INDEX@@|${suffix}|g" \
      -e "s|@@CAPACITY@@|${PV_SIZE_K8S}|g" \
      -e "s|@@PATH@@|${volumes_root}/pv${suffix}|g" \
      -e "s|@@NODE_NAME@@|${node_name}|g" \
      "${SCRIPT_DIR}/persistent-volume.yaml.in"
  } >> "$storage_manifest"
done

k0s kubectl apply -f "$storage_manifest"

printf '\nInstallation complete.\n\n'
k0s status
printf '\n'
k0s kubectl get nodes -o wide
printf '\n'
k0s kubectl get storageclass,persistentvolume
printf '\nZFS datasets:\n'
zfs list -r -o name,used,avail,mountpoint \
  "$K0S_DATASET" "$CONTAINERD_DATASET" "$VOLUMES_DATASET"
