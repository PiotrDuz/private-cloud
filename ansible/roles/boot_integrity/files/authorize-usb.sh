#!/bin/bash
# Authorizes one USB device on the root disk path and binds only its interfaces of one class.
# udev runs this in the initrd and on the host; other functions of the device never get a driver.

NAME=$1
CLASS=$2
DEVICES=/sys/bus/usb/devices
BUS=${NAME%%-*}
HUB=$DEVICES/usb$BUS/interface_authorized_default

main() {
    if [ "$(field "$DEVICES/$NAME/authorized")" != 1 ]; then
        echo 0 > "$HUB"
        echo 1 > "$DEVICES/$NAME/authorized"
        echo 1 > "$HUB"
        restore_interfaces
    fi
    filter_interfaces
}

filter_interfaces() {
    local interface
    for interface in "$DEVICES/$NAME/$NAME":*; do
        [ -d "$interface" ] || continue
        if [ "$(field "$interface/bInterfaceClass")" = "$CLASS" ]; then
            authorize_interface "$interface"
        else
            echo 0 > "$interface/authorized"
        fi
    done
}

# Interfaces that other devices on the bus created while the hub default was 0.
restore_interfaces() {
    local interface name
    for interface in "$DEVICES/$BUS"-*:*; do
        name=${interface##*/}
        case $name in "$NAME":*) continue ;; esac
        [ "$(field "$DEVICES/${name%%:*}/authorized")" = 1 ] || continue
        authorize_interface "$interface"
    done
}

authorize_interface() {
    [ "$(field "$1/authorized")" = 1 ] && return 0
    echo 1 > "$1/authorized"
    echo "${1##*/}" > /sys/bus/usb/drivers_probe
}

field() {
    local value=
    { read -r value < "$1"; } 2> /dev/null || value=
    printf '%s' "$value"
}

main
