#!/bin/sh
set -eu

root_dataset="$1"

if [ "$(/usr/sbin/zfs get -H -o value keystatus "$root_dataset")" = "unavailable" ]; then
  /usr/sbin/zfs load-key "$root_dataset"
fi

if [ "$(/usr/sbin/zfs get -H -o value mounted "$root_dataset")" != "yes" ]; then
  /usr/sbin/zfs mount "$root_dataset"
fi

/usr/sbin/zfs mount -a
