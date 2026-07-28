#!bin/bash
echo "Installig ZFS"
sudo apt update
sudo apt install zfsutils-linux
sudo modprobe zfs
echo "Is zfs installed?"
sudo zfs version
echo "Is zed installed?"
systemctl status zfs-zed.service

echo "Discover disks"
lsblk -e 7 -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL,SERIAL,TRAN
#-> note which disks are to be used as zfs, but need to extract their uuids
# udevadm info --query=symlink --name=/dev/sdb
ls -l /dev/disk/by-id/$id
readlink -f /dev/disk/by-id/$id # - should resolve to /dev/sdX

echo "Creating ZFS pool"
# Intended for SSD-backed deployments. TRIM is issued only when the complete
# storage path exposes discard/UNMAP support; verify that later with lsblk -D.
zpool create -o autotrim=on tank raidz1 "$DISK1" "$DISK2"
 sudo zpool status -v tank # - check status
sudo zpool get autotrim tank # verify SSD discard is enabled for the pool

echo " creating secure dataset "
# passphrase saved in key file, so can still be unlocked without file
printf '%s' 'password' | sudo tee /etc/zfs/keys/tank-secure.key >/dev/null
sudo chmod 600 /etc/zfs/keys/tank-secure.key
sudo zfs create \
  -o encryption=aes-256-gcm \
  -o keyformat=passphrase \
  -o keylocation=file:///etc/zfs/keys/tank-secure.key \
  -o compression=zstd \
  tank/secure

echo " configure ZED "
sudo apt install zfs-zed
sudo systemctl enable --now zfs-zed.service

echo " monthly scrubs " 
sudo systemctl enable --now zfs-scrub-monthly@tank.timer
systemctl list-timers zfs-scrub-monthly@tank.timer # - verify
