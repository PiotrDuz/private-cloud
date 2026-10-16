#!/bin/bash
# Unattended LUKS unlock from TPM NV memory; runs in the initrd before systemd-cryptsetup.
# Every path ends with exit 0 so a failed check falls through to the recovery passphrase prompt.

CONFIGURATION=${PRIVATE_CLOUD_CONFIGURATION:-/etc/private-cloud/boot-integrity.conf}
RUN=${PRIVATE_CLOUD_RUN:-/run/private-cloud}
KEY_DIRECTORY=${PRIVATE_CLOUD_KEY_DIRECTORY:-/run/cryptsetup-keys.d}
INVENTORY=${PRIVATE_CLOUD_INVENTORY:-/usr/lib/private-cloud/inventory.sh}
TPM_DEVICE=${PRIVATE_CLOUD_TPM_DEVICE:-/dev/tpmrm0}
STATE=0x01500010
RECORD=0x01500011
KEY=0x01500012
INVENTORY_WAIT=${PRIVATE_CLOUD_INVENTORY_WAIT:-60}
GATEWAY_WAIT=${PRIVATE_CLOUD_GATEWAY_WAIT:-120}
POWER_OFF=
INVENTORY_TEXT=

# shellcheck source=/dev/null
. "$CONFIGURATION"
: "${TPM2TOOLS_TCTI:=device:$TPM_DEVICE}"
export TPM2TOOLS_TCTI

main() {
    mkdir -p "$RUN" "$KEY_DIRECTORY"
    wait_for_tpm || finish "error:no-tpm"
    case "$(read_state)" in
        armed) unlock ;;
        wiped)
            zero_indexes
            inert wiped
            ;;
        unenrolled) inert unenrolled ;;
        *) finish "error:state" ;;
    esac
}

unlock() {
    local record salt gateway expected measurement status

    record=$(nv_read "$RECORD" "$PCRS,11")
    status=$?
    [ "$status" -eq 0 ] || read_failed "$status" record
    nv_lock "$RECORD" "$PCRS,11"
    salt=${record:0:64}
    gateway=${record:64:12}
    expected=${record:76:64}
    [[ $salt =~ [^0] ]] || wipe record-empty

    wait_inventory "$expected" || wipe inventory-mismatch
    join_network || finish "error:no-interface"
    wait_gateway "$expected" "$gateway"

    measurement=$(printf '%s\n%s\n%s\n' "$salt" "$INVENTORY_TEXT" "$gateway" | sha256sum | cut -d' ' -f1)
    pcr15_unused || finish "error:pcr15-used"
    tpm2_pcrextend "15:sha256=$measurement" > /dev/null 2>&1 || finish "error:extend"

    (umask 077 && : > "$KEY_DIRECTORY/$LUKS_VOLUME.key" && nv_read "$KEY" "$PCRS,11,15" "$KEY_DIRECTORY/$LUKS_VOLUME.key" > /dev/null)
    status=$?
    [ "$status" -eq 0 ] || { rm -f "$KEY_DIRECTORY/$LUKS_VOLUME.key"; read_failed "$status" key; }
    chmod 0400 "$KEY_DIRECTORY/$LUKS_VOLUME.key"
    nv_lock "$KEY" "$PCRS,11,15"
    finish unlocked
}

inert() {
    INVENTORY_TEXT=$(settle_inventory)
    finish "inert:$1"
}

cleanup() {
    rm -f "$KEY_DIRECTORY/$LUKS_VOLUME.key"
}

wait_for_tpm() {
    local waited=0
    udevadm settle --timeout=10 > /dev/null 2>&1
    until [ -c "$TPM_DEVICE" ] || [ "$waited" -ge 20 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    [ -c "$TPM_DEVICE" ]
}

read_state() {
    local attempt value
    for attempt in 1 2 3; do
        if tpm2_nvread "$STATE" -C "$STATE" > "$RUN/state.out" 2> "$RUN/state.err"; then
            value=$(od -An -v -tx1 "$RUN/state.out" | tr -d ' \n')
            [ "$value" = 01 ] && echo armed || echo wiped
            return
        fi
        if grep -q 0x18B "$RUN/state.err"; then
            echo unenrolled
            return
        fi
        sleep 1
    done
    echo error
}

# Prints the NV contents as hex, or writes them to $3. Returns 2 on a policy failure and 3 on any other failure.
nv_read() {
    local handle=$1 pcrs=$2 output=${3:-$RUN/nv.out} attempt status
    for attempt in 1 2 3; do
        policy_session "$pcrs" || { sleep 1; continue; }
        tpm2_nvread "$handle" -C "$handle" -P "session:$RUN/session.ctx" -o "$output" > /dev/null 2> "$RUN/nv.err"
        status=$?
        tpm2_flushcontext "$RUN/session.ctx" > /dev/null 2>&1
        if [ "$status" -eq 0 ]; then
            [ -n "${3:-}" ] || od -An -v -tx1 "$output" | tr -d ' \n'
            [ -n "${3:-}" ] || rm -f "$output"
            return 0
        fi
        if grep -qi -e 0x99D -e 'policy check failed' "$RUN/nv.err"; then
            log_pcrs "$pcrs"
            return 2
        fi
        sleep 1
    done
    return 3
}

nv_lock() {
    policy_session "$2" || return 1
    tpm2_nvreadlock "$1" -C "$1" -P "session:$RUN/session.ctx" > /dev/null 2>&1
    tpm2_flushcontext "$RUN/session.ctx" > /dev/null 2>&1
}

policy_session() {
    tpm2_startauthsession --policy-session -S "$RUN/session.ctx" > /dev/null 2>&1 || return 1
    tpm2_policypcr -S "$RUN/session.ctx" -l "sha256:$1" > /dev/null 2>&1 && return 0
    tpm2_flushcontext "$RUN/session.ctx" > /dev/null 2>&1
    return 1
}

read_failed() {
    [ "$1" -eq 2 ] && wipe "$2-policy"
    finish "error:tpm-$2"
}

wipe() {
    zero_indexes
    finish "wiped:$1"
}

wipe_and_power_off() {
    POWER_OFF=1
    wipe "$1"
}

zero_indexes() {
    head -c 64 /dev/zero | tpm2_nvwrite "$KEY" -C "$KEY" -i- > /dev/null 2>&1
    head -c 128 /dev/zero | tpm2_nvwrite "$RECORD" -C "$RECORD" -i- > /dev/null 2>&1
    printf '\000' | tpm2_nvwrite "$STATE" -C "$STATE" -i- > /dev/null 2>&1
}

wait_inventory() {
    local deadline=$((SECONDS + INVENTORY_WAIT))
    while :; do
        INVENTORY_TEXT=$("$INVENTORY")
        [ "$(digest_of "$INVENTORY_TEXT")" = "$1" ] && return 0
        [ "$SECONDS" -ge "$deadline" ] && return 1
        sleep 1
    done
}

settle_inventory() {
    local previous= current= stable=0 waited=0
    while [ "$stable" -lt 3 ] && [ "$waited" -lt 40 ]; do
        current=$("$INVENTORY")
        if [ "$current" = "$previous" ]; then stable=$((stable + 1)); else stable=0; fi
        previous=$current
        sleep 2
        waited=$((waited + 2))
    done
    printf '%s' "$current"
}

join_network() {
    local waited=0
    until [ -e "/sys/class/net/$INTERFACE" ] || [ "$waited" -ge 30 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    [ -e "/sys/class/net/$INTERFACE" ] || return 1
    ip link set "$INTERFACE" up
    ip addr add "$HOST_ADDRESS" dev "$INTERFACE" 2> /dev/null
    return 0
}

# A changed inventory or another gateway wipes; a gateway that stays silent past the limit wipes and powers off.
wait_gateway() {
    local macs deadline=$((SECONDS + GATEWAY_WAIT))
    while :; do
        INVENTORY_TEXT=$("$INVENTORY")
        [ "$(digest_of "$INVENTORY_TEXT")" = "$1" ] || wipe inventory-changed
        macs=$(gateway_macs)
        if [ -n "$macs" ]; then
            [[ " $macs " == *" $2 "* ]] && return 0
            wipe gateway-mismatch
        fi
        [ "$SECONDS" -ge "$deadline" ] && wipe_and_power_off gateway-timeout
        sleep 2
    done
}

gateway_macs() {
    arping -c 1 -w 2 -I "$INTERFACE" "$GATEWAY_IP" 2> /dev/null \
        | grep -o '\[[0-9A-Fa-f:]*\]' | tr -d '[]:' | tr 'A-F' 'a-f' | sort -u | tr '\n' ' ' | sed 's/ $//'
}

digest_of() {
    printf '%s\n' "$1" | sha256sum | cut -d' ' -f1
}

pcr15_unused() {
    tpm2_pcrread -o "$RUN/pcr15.bin" sha256:15 > /dev/null 2>&1 || return 1
    [[ $(od -An -v -tx1 "$RUN/pcr15.bin" | tr -d ' \n') =~ ^0+$ ]]
}

log_pcrs() {
    echo "private-cloud-tpm: policy check failed for PCRs $1" >&2
    tpm2_pcrread "sha256:$1" >&2 2> /dev/null
}

authorize_usb() {
    local attribute
    for attribute in /sys/bus/usb/devices/usb*/authorized_default /sys/bus/usb/devices/*/authorized; do
        [ -e "$attribute" ] && { echo 1 > "$attribute"; } 2> /dev/null
    done
    return 0
}

finish() {
    [ -n "$INVENTORY_TEXT" ] || INVENTORY_TEXT=$("$INVENTORY")
    printf '%s\n' "$INVENTORY_TEXT" > "$RUN/initrd-inventory"
    printf '%s\n' "$1" > "$RUN/unlock-result"
    rm -f "$RUN"/nv.out "$RUN"/nv.err "$RUN"/state.out "$RUN"/state.err "$RUN"/session.ctx "$RUN"/pcr15.bin
    echo "private-cloud-tpm: $1"
    [ -z "$POWER_OFF" ] || power_off
    [ "$1" = unlocked ] || authorize_usb
    exit 0
}

power_off() {
    systemctl poweroff --force || echo o > /proc/sysrq-trigger
    sleep 30
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-unlock}" in
        cleanup) cleanup ;;
        *) main ;;
    esac
fi
