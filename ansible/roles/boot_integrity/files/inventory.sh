#!/bin/bash
# Prints the canonical hardware inventory; the initrd and the installer run this same file.

export LC_ALL=C

main() {
    {
        pci_devices
        usb_devices
        disks
        network_cards
        board
    } | sort
}

pci_devices() {
    local device
    for device in /sys/bus/pci/devices/*; do
        [ -d "$device" ] || continue
        printf 'pci %s %s:%s %s:%s class=%s\n' "${device##*/}" \
            "$(field "$device/vendor")" "$(field "$device/device")" \
            "$(field "$device/subsystem_vendor")" "$(field "$device/subsystem_device")" \
            "$(field "$device/class")"
    done
}

usb_devices() {
    local device
    for device in /sys/bus/usb/devices/*; do
        [ -r "$device/idVendor" ] || continue
        printf 'usb %s %s:%s serial=%s\n' "${device##*/}" \
            "$(field "$device/idVendor")" "$(field "$device/idProduct")" "$(field "$device/serial")"
    done
}

disks() {
    local disk
    for disk in /sys/block/*; do
        case "${disk##*/}" in loop* | ram* | zram* | dm-* | md* | zd* | nbd* | sr*) continue ;; esac
        [ -e "$disk/device" ] || continue
        printf 'disk %s %s %s %s\n' "$(field "$disk/device/vendor")" "$(field "$disk/device/model")" \
            "$(field "$disk/device/serial")" "$(field "$disk/device/wwid")"
    done
}

network_cards() {
    local card
    for card in /sys/class/net/*; do
        [ -e "$card/device" ] || continue
        printf 'net %s\n' "$(field "$card/address")"
    done
}

board() {
    local name
    for name in board_vendor board_name board_serial product_uuid; do
        printf 'dmi %s %s\n' "$name" "$(field "/sys/class/dmi/id/$name")"
    done
    printf 'cpu %s\n' "$(sed -n 's/^model name[[:space:]]*:[[:space:]]*//p' /proc/cpuinfo | head -n 1)"
}

field() {
    local value=
    { read -r value < "$1"; } 2> /dev/null || value=
    printf '%s' "$value"
}

main
