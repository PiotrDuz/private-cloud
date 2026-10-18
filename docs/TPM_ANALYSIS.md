# TPM unattended unlock analysis

Last updated: 16 October 2026.

Status: implemented in the `boot_integrity` stage and verified against a software TPM; live-host acceptance is pending in [TODO.md](../TODO.md#boot-integrity-acceptance). The major decisions are in [PLAN.md](../PLAN.md#tpm-unattended-unlock).

Accepted by the operator on 16 October 2026:

- Running-host mitigations in [decision 10](#10-running-host-hardening).
- Firmware settings as manual steps in [SETUP.md](SETUP.md#boot-integrity).
- No automatic kernel, firmware, or boot-chain updates.
- An inert wiped state that runs no checks and allows console login with the administrator password.

## Goal

- Boot and unlock without any input after a power loss.
- Make a stolen host, or its disks, much harder to read than copying a key file.
- Refuse to unlock after any change to firmware, boot chain, hardware, attached devices, or network.
- Destroy the unattended unlock secret when a check fails, so an attacker gets one attempt.
- Stop all checks once the secret is destroyed, so the operator can attach a keyboard without reboot loops.
- Keep a recovery passphrase as the only fallback.

## Assumptions

- The root disk is LUKS2 with a recovery passphrase, created by the Ubuntu installer; see [SETUP.md](SETUP.md#host-installation).
- Ubuntu 26.04 LTS with systemd 259 and dracut as the initrd generator.
- Intel N305 with Intel PTT, a firmware TPM 2.0 inside the chipset.
- The `tank/secure` key file stays at `/etc/zfs/keys/tank-secure.key` on the encrypted root.
- The Ubuntu administrator account created at install time is the host administrator.
- The operator is physically present for kernel and firmware updates and accepts a passphrase entry after each.

## Threat model

In scope:

- Theft of the powered-off host, with unlimited time and tooling.
- Theft of individual disks.
- Offline modification of the ESP, firmware settings, or attached hardware before the next boot.
- Booting the stolen host on another network, including with the stolen router.
- Physical access to the running host through USB ports, the console, and DMA-capable slots.

Out of scope:

- Remote compromise of the running host; the data is unlocked while it runs.
- Cold-boot RAM extraction and invasive attacks on the chipset.
- Vulnerabilities in Intel CSME firmware that expose PTT.

## Current state and gap

`tank/secure` loads its key from a plaintext file on the system disk. Anyone holding the disk reads the key.

Encrypting root with LUKS fixes that only while the passphrase is required at boot. Any unattended unlock must therefore come from the TPM, and the TPM must refuse to release the secret to anything except this host's untouched boot chain, on this host's hardware, on this network.

The TPM measures firmware, bootloader, kernel, and initrd into PCRs. It never measures the root filesystem. Encrypted root is what makes that sufficient: an attacker cannot plant code on root without the key, and cannot change the measured boot chain without changing the PCRs.

## Design overview

```
firmware (PCR 0, 2) ── Secure Boot, owner keys only (PCR 7)
  └─ signed UKI on the ESP (PCR 4; sections into PCR 11; phase enter-initrd into PCR 11)
       └─ initrd unlock hook
            0. state index says wiped → authorize USB, recovery prompt, no checks
            1. read the boot record from TPM NV, then read-lock it
            2. wait for the hardware inventory and the gateway
            3. gateway mismatch or USB attach → wipe → recovery prompt
            4. extend PCR 15 with H(salt ‖ hardware inventory ‖ gateway MAC)
            5. read the LUKS key from TPM NV, then read-lock it
            6. read failure → wipe → recovery prompt
            7. hand the key to systemd-cryptsetup, delete it from /run
  └─ root mounted → zfs-load-key@tank-secure from /etc/zfs/keys → k0s
  └─ armed: tripwires on, no console login
  └─ wiped: tripwires off, USB allowed, console login with the administrator password
```

## Decisions

### 1. Boot chain: owner Secure Boot keys and a directly booted UKI

- Enroll owner PK, KEK, and db keys and remove the Microsoft keys.
- Boot one Unified Kernel Image directly from a UEFI boot entry, without shim or GRUB.
- Build the UKI with `ukify` from the Ubuntu kernel, the dracut initrd, and a fixed kernel command line.
- Rely on systemd-stub ignoring command line overrides while Secure Boot is on.

Why: only binaries signed with the owner db key run, and the kernel command line cannot be edited at the boot menu. The N305 iGPU uses the firmware's built-in GOP driver, so the Microsoft UEFI CA for option ROMs should not be needed; confirm before removing it, or the screen stays dark.

Ubuntu's own TPM-backed encryption seals to the Canonical-signed snap boot chain and cannot carry the checks below, so it is not used.

### 2. The unattended key lives in TPM NV memory, not in the LUKS header

- Add a random 64-character key to LUKS slot 7 with a fast PBKDF, because the key already has full entropy.
- Store that key only in a TPM NV index, never on disk.
- Define the index with `authwrite|policyread|read_stclear`, an empty write authorization, and a PolicyPCR read policy.
- Read-lock the index right after the read, so a read lock lasts until the next reboot.

Why: `systemd-cryptenroll` and `systemd-pcrlock` store a sealed blob in the LUKS header or rely on an NV policy that can be restored. An attacker who images the header first can undo a wipe. Overwriting an NV index that holds the key itself destroys the secret permanently. The empty write authorization lets the initrd and the tripwire wipe without any stored credential, and it works even when the PCRs no longer match. An attacker can write too, but that only destroys the key and does not reveal it.

The index authorization cannot be changed without satisfying the PCR policy, so an attacker cannot lock the wipe path by changing it. Setting the owner hierarchy authorization does not affect the wipe either.

### 3. Armed and wiped states

- Keep a one-byte public state index in TPM NV that anyone can read and write.
- Write `armed` only from re-enrollment.
- Wipe in this order: zero the key, zero the boot record, then write `wiped`.
- Treat an `armed` state with a zeroed or invalid boot record as `wiped`, and correct the state index.
- In the wiped state, zero the key and boot record again before showing the recovery prompt.
- In the wiped state, skip the gateway wait, the inventory wait, and all tripwires.
- In the wiped state, authorize all USB devices and start a console login.
- Never reboot from any check; failures either show the recovery prompt or power off.

Why: once the key is gone, the checks protect nothing. Running them anyway would turn an attached keyboard into a wipe-and-power-off loop. The state index needs no protection: forging `wiped` only forces a recovery prompt and destroys the key, and forging `armed` cannot recreate a key that is gone.

The operator then needs two secrets at the console: the LUKS recovery passphrase in the initrd and the administrator password at login.

### 4. PCR selection

| PCR | Contents | Changes when |
| --- | --- | --- |
| 0 | Firmware code | Firmware update |
| 1 | Firmware configuration | Settings, boot order, and on some boards attached devices |
| 2 | Option ROM code | PCIe card with an option ROM added |
| 4 | Boot applications loaded | Any other EFI binary runs first, or the UKI changes |
| 5 | Boot disk GPT and boot variables | Partition table or boot entries change |
| 7 | Secure Boot state and the certificate that verified the UKI | Secure Boot off, keys changed, CMOS reset |
| 11 | UKI sections and the boot phase | Kernel, initrd, or command line change; after leaving the initrd |
| 15 | Salted hardware and gateway inventory from the initrd | Any device, disk, NIC, or gateway change |

- Bind the key to PCRs 0, 2, 4, 7, 11, and 15.
- Add PCRs 1 and 5 only if their values stay identical across three cold boots on this board.
- Predict PCR 11 for the `enter-initrd` phase with `systemd-measure calculate`.
- Use literal PCR values, not a signed PCR policy.

Why literal values: a signed PCR 11 policy (the "UKI signing" scheme, PolicyAuthorize in systemd) exists so updates keep unlocking without re-enrollment. The operator re-enrolls after every update anyway, and a literal policy accepts exactly one UKI instead of every UKI the key ever signed. Secure Boot signing of the UKI is still required.

### 5. One unseal per boot

- Read-lock the key and boot record indexes right after reading them.
- Include PCR 11 at its `enter-initrd` value, which systemd extends to `leave-initrd`, `sysinit`, and `ready` later in the boot.

Why: root on the running system, including a remote attacker, cannot read the key again.

### 6. Hardware inventory in PCR 15

- Measure PCI vendor, device, subsystem, and slot IDs.
- Measure USB vendor, product, and serial for every device, including internal hubs.
- Measure disk model and serial for every block device.
- Measure NIC MAC addresses and the DMI board serial and system UUID.
- Wait for udev to settle and for the inventory to match the expected digest for up to 60 seconds before measuring.

Why: PCRs do not cover USB devices or most hardware. The measuring code runs inside the signed UKI, so an attacker cannot fake the measurement without changing PCR 4, 7, or 11. Waiting for the expected digest prevents a false wipe when USB enumeration is slow.

### 7. Gateway check with a salted measurement

- Store a boot record NV index with a random salt, the expected gateway MAC, and the expected inventory digest.
- Gate the record's read on PCRs 0, 2, 4, 7, and 11, and read-lock it after reading.
- Bring up the LAN with a static address in the initrd and ARP the gateway.
- Wait up to 2 minutes for the gateway to answer.
- Wipe and power off when the gateway stays silent for 2 minutes.
- Wipe when a different MAC answers.
- Mix the salt into the PCR 15 measurement.

Why: the NV index's public policy digest is readable by anyone. Without a salt, an attacker could compute PCR 15 for each candidate gateway MAC offline, learn the right MAC, and spoof it. The salt is readable only by this boot chain, so guessing must happen online, where the first wrong guess wipes the key. The 2-minute limit gives a router that boots slower than the host time to answer, and a host with no gateway at all cannot sit waiting for an attacker's guess. A power outage that outlasts the router's boot by more than 2 minutes wipes the unlock and leaves the host off until the operator re-enrolls.

A MAC check proves only that a device with that MAC answers. It does not stop a thief who takes the router too. A Tang server hidden elsewhere in the LAN (Clevis network-bound encryption) is the stronger option; see [Open questions](#open-questions).

### 8. Wipe rules

| Condition | Action |
| --- | --- |
| State index says wiped | Zero the key again, authorize USB, recovery prompt |
| Gateway silent for 2 minutes | Wipe, then power off |
| USB device attached during the initrd waits | Wipe, then recovery prompt |
| Gateway answers with another MAC | Wipe, then recovery prompt |
| Inventory still differs after 60 seconds | Measure it anyway; the key read fails and wipes |
| Key read fails with a policy error | Wipe, then recovery prompt |
| No TPM device or a transport error | Recovery prompt without wipe |
| Armed host, USB device attached at runtime | Wipe, then power off |
| Armed host, another gateway MAC at runtime | Wipe, then power off |

- Wipe by overwriting the key and boot record indexes with zeros, then marking the state `wiped`.
- Kill the TPM LUKS keyslot during the next re-enrollment, not from the initrd.

Why: the TPM's dictionary-attack lockout counts only failed authorization values, such as PINs. PCR mismatches are not counted, so a retry limit never trips without a PIN. The wipe is the retry limit, and it allows one attempt. Attaching a keyboard during the initrd waits is also the operator's way into the recovery prompt when the gateway is gone for good.

### 9. Runtime tripwires

- Arm the tripwire service only when the state index says `armed`.
- Boot with `usbcore.authorized_default=2` so newly attached external USB devices get no driver.
- Poll USB and PCI devices every 0.5 seconds against the set present 20 seconds after boot.
- On any new device, wipe and power off.
- Every 30 seconds, ARP the gateway; wipe and power off when replies arrive and none carries the enrolled MAC.
- Disarm the tripwire before planned maintenance with `systemctl stop private-cloud-tripwire.service`.

Why power off and not reboot: a reboot would give a thief a host that unlocks itself again. Power off clears the keys from RAM. The next boot sees the wiped state and runs no checks, so there is no loop. A proxy-ARP device answering next to the real gateway does not trip the wipe.

`authorized_default=2` relies on ACPI marking the ports as internal. Check on this board which devices it leaves unauthorized.

#### USB system disk

- Detect whether the LUKS device sits behind USB from its sysfs path.
- Write a udev rule for that port, vendor, product, and serial into the host and the initrd.
- Bind only mass-storage interfaces on the disk adapter and hub interfaces on hubs along the path.
- Write no rule for an internal SATA or NVMe system disk.

Why: the port is removable, so `authorized_default=2` would hide the system disk in the initrd. An adapter with a zero serial can be replaced by a composite device with the same IDs. Binding only the storage interface leaves an added keyboard or network function without a driver. The disk serial in PCR 15 still detects a swapped disk.

### 10. Running-host hardening

- Enable VT-d with strict IOMMU invalidation (`intel_iommu=on iommu.strict=1`).
- Boot with `lockdown=confidentiality`.
- Disable magic SysRq.
- Start no local console login while armed.
- Start a console login on tty1 only in the wiped state, with the administrator password and no autologin.
- Disable the initrd shells, as described in [decision 11](#11-initrd-lockdown).
- Check the firmware for Total Memory Encryption and enable it if offered.
- Verify that Alloy, Zabbix, and Intel GPU workloads still work under lockdown.

Why: a running host is decrypted, so its physical interfaces are the attack surface. Strict IOMMU blocks DMA from PCIe and M.2 devices. Lockdown keeps even root from reading kernel memory, where the LUKS and ZFS keys live. Without a console login and with USB unauthorized, a keyboard gives nothing while armed.

### 11. Initrd lockdown

- Set `rd.shell=0` and `rd.emergency=poweroff`.
- Mask the emergency and debug shells in the initrd.
- Authorize external USB keyboards only in the wiped state, which every failure path enters first.
- Delete the key from `/run/cryptsetup-keys.d/` after unlock, because `/run` survives the switch to root.

Why: an initrd root shell before the PCR 15 measurement could extend the expected value by hand and read the key. Without a shell, the only code running at that point is the signed unlock hook.

### 12. No automatic boot-chain updates

- Disable automatic installation of kernel, linux-firmware, microcode, dracut, cryptsetup, and systemd-boot packages.
- Hold the kernel packages so apt does not remove the modules that the booted UKI needs.
- Disable automatic firmware updates through fwupd.
- Keep the UKI rebuild manual, outside kernel postinst hooks.
- Leave automatic updates for other packages enabled.

Why: an update that changes the booted UKI or firmware changes the PCRs. Followed by an unattended power loss, it would wipe the key and leave the host at the recovery prompt while the operator is away.

### 13. Signing keys stay off the host

- Keep the Secure Boot PK, KEK, and db private keys on the operator's workstation.
- Sign each new UKI on the workstation and copy it back.

Why: a remote attacker with root could otherwise sign a persistent malicious UKI. The literal PCR policy needs no signing key on the host.

Firmware settings are manual steps; see [SETUP.md](SETUP.md#boot-integrity). A CMOS reset clears the firmware password but also resets Secure Boot, which changes PCR 7 and fails safely.

## Boot flow

1. Firmware measures itself, verifies the UKI against the owner db key, and boots it.
2. systemd-stub measures the UKI sections into PCR 11, and the initrd extends PCR 11 with `enter-initrd`.
3. The unlock hook reads the state index; if it says wiped, it goes to step 9.
4. The hook reads the boot record and read-locks it.
5. The hook brings up the LAN, waits for the gateway, and compares its MAC.
6. The hook waits for the inventory, extends PCR 15, reads the key, and read-locks it.
7. The hook writes the key to `/run/cryptsetup-keys.d/<volume>.key` for systemd-cryptsetup.
8. systemd-cryptsetup unlocks root, the hook deletes the key file, and the boot continues armed at step 10.
9. On any failure path, the hook wipes, authorizes USB, and systemd-cryptsetup prompts for the passphrase.
10. ZFS loads `tank/secure` from the key file, and k0s starts.
11. An armed host arms the tripwires; a wiped host starts the console login instead.

## Original ideas

| Idea | Verdict |
| --- | --- |
| TPM unlock without input | Yes, with encrypted root and an initrd unlock hook |
| UKI signing so the unlocking system cannot be swapped | Yes, through owner Secure Boot keys and a literal PCR 4, 7, and 11 policy |
| Catching the key on the TPM bus | Not possible: PTT is inside the chipset, with no external bus |
| Trip on any hardware change | Yes, through the PCR 15 inventory and PCRs 0 and 2 |
| Trip on attached USB devices | Yes, at boot through PCR 15 and at runtime through the tripwire |
| USB attach clears the TPM and restarts | Wipe and power off, not restart |
| Clear the TPM on failed checks | Wipe the NV indexes; a full TPM clear needs lockout authorization and adds nothing |
| Low retry count or long lockout | The lockout does not count PCR mismatches; the wipe gives one attempt |
| Router MAC check | Yes, salted and checked in the initrd and at runtime; Tang is stronger |
| System updates trip the TPM | Accepted; boot-chain updates are manual, followed by re-enrollment |
| No checks once the TPM is cleared | Yes, through the wiped state, with console login by administrator password |

## Residual risks

- A thief who keeps the host powered, avoids the USB ports, and keeps the network intact meets only the network attack surface.
- Cold-boot RAM extraction after a forced power off remains possible within minutes.
- A thief who takes the router as well passes the MAC check; only Tang or another separate factor stops that.
- Intel CSME vulnerabilities could expose PTT contents; keep the firmware current through manual updates.
- A firmware update may reset PTT and lose the key; the recovery passphrase covers that.
- The recovery passphrase is the remaining offline target; LUKS2 Argon2id slows guessing, so make it long and random.
- The administrator password guards the console in the wiped state; it needs the same strength.
- Held kernel packages delay kernel security fixes until the next maintenance visit.
- Cheap N305 boards may ship incomplete firmware: missing Setup Mode, unstable PCR 1, or broken PTT NV persistence.

## Operations

Update:

1. Disarm the tripwire with `systemctl stop private-cloud-tripwire.service` if a keyboard is needed on the running host.
2. Install the held boot-chain packages over SSH.
3. Run the installer; it builds a new unsigned UKI and its PCR 11 manifest.
4. Sign the UKI on the workstation and copy `signed.efi` back.
5. Rerun the installer to place the UKI on the ESP.
6. Reboot; the key read fails, the hook wipes, and the recovery prompt appears.
7. Attach a keyboard, enter the recovery passphrase, and log in with the administrator password.
8. Unplug the keyboard and every other external USB device except a USB system disk.
9. Rerun the installer, confirm the gateway MAC and USB list, and enter the recovery passphrase.
10. Reboot and confirm an unattended unlock.

Recovery after a tripwire, a move, or a failed check uses steps 7 to 10.

Enrollment shows the USB devices it binds and asks for confirmation, because the inventory would include an attached keyboard.

## Repository impact

- `ansible/roles/boot_integrity/` is the stage; it runs right after the system role.
- `ansible/tpm_nv.py` holds the TPM NV primitives shared by the installer and the host tripwire.
- `ansible/boot_integrity_helpers.py` holds enrollment and the stage validation checks.
- `ansible/boot_settings.py` holds the shared paths and the settings parser.
- The dracut module `90private-cloud-tpm` is shell, because the initrd has no Python.
- `inventory.sh` runs in both the initrd and the host, so both compute the same digest.
- `uki.py` builds the unsigned UKI and its PCR 11 manifest, then installs the signed UKI.
- `tripwire.py` runs the tripwire and the console policy.
- `boot-integrity/workstation.py` creates the owner keys and signs the UKI on the workstation.
- The public configuration gains the `boot_integrity` section and stage; schema version is 14.
- The stage is off by default in the example configuration.
- The installer enrolls the unlock after the playbook when the host booted the signed UKI.
- The ZFS role and its key file path are unchanged.

## Verification status

Verified against a software TPM with the real scripts:

- NV definition, empty-auth writes, PolicyPCR reads, read lock, and policy-failure detection.
- Unlock, gateway mismatch, gateway timeout with power-off, late gateway answer, hardware change, boot-chain change, wiped, unenrolled, and keyboard-while-waiting paths of the initrd hook.
- Agreement between the enrollment code and the hook on the record layout, the PCR 15 value, and the released key.
- Tripwire wipe on a new device and on another gateway, and the console policy.
- `ukify` measurement of the exact section set, including `.sbat`.
- Schema validation of the new configuration section.

Not verified without the live host:

- The dracut build of the initrd and the systemd ordering inside it.
- Real firmware PCR stability, Secure Boot enrollment, and PTT persistence.
- `arping` output on the real network and the `usbcore.authorized_default=2` behavior.
- The `cryptsetup` slot handling and the unattended reboot.

## Open questions

- Can the router, or another device hidden on the LAN, run a Tang server?
- Should the recovery passphrase also be accepted over SSH from the initrd, for remote recovery after a power loss? This trusts an initrd host key stored on the ESP.
- Should the 10-minute link-down power off be enabled?

## Sources

- [systemd-pcrlock(8)](https://man.archlinux.org/man/systemd-pcrlock.8.en)
- [Ubuntu 26.04 dracut configuration](https://linuxconfig.org/how-to-configure-dracut-initramfs-on-ubuntu-26-04)
- [Ubuntu switch to dracut specification](https://discourse.ubuntu.com/t/spec-switch-to-dracut/54776)
- [Ubuntu 26.04 release features](https://linuxconfig.org/ubuntu-26-04-release-date-and-new-features-in-resolute-raccoon)
