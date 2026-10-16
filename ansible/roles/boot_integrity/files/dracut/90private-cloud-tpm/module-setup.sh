#!/bin/bash

check() {
    require_binaries tpm2_nvread tpm2_nvwrite tpm2_nvreadlock tpm2_policypcr tpm2_startauthsession \
        tpm2_flushcontext tpm2_pcrread tpm2_pcrextend arping ip sha256sum od || return 1
    return 255
}

depends() {
    echo systemd systemd-cryptsetup systemd-pcrextend tpm2-tss
    return 0
}

installkernel() {
    hostonly='' instmods tpm tpm_crb tpm_tis tpm_tis_core xhci_pci xhci_hcd ehci_pci usbhid hid hid_generic nvme ahci libahci sd_mod
}

install() {
    inst_multiple tpm2_nvread tpm2_nvwrite tpm2_nvreadlock tpm2_policypcr tpm2_startauthsession \
        tpm2_flushcontext tpm2_pcrread tpm2_pcrextend arping ip udevadm sha256sum od tr cut sed grep head sort sleep rm chmod mkdir
    inst_simple "$moddir/unlock.sh" /usr/lib/private-cloud/unlock.sh
    inst_simple /usr/local/libexec/private-cloud/inventory.sh /usr/lib/private-cloud/inventory.sh
    inst_simple /etc/private-cloud/boot-integrity.conf /etc/private-cloud/boot-integrity.conf
    inst_simple "$moddir/system.conf" /etc/systemd/system.conf.d/90-private-cloud.conf
    inst_simple "$moddir/private-cloud-tpm-unlock.service" "$systemdsystemunitdir/private-cloud-tpm-unlock.service"
    $SYSTEMCTL -q --root "$initdir" add-wants cryptsetup-pre.target private-cloud-tpm-unlock.service
}
