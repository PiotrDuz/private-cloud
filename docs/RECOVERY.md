# Recovery runbook

Use the completed [operator record](OPERATOR_RECORD.md) and a known-good recovery point.

Do not run the installer against an uncertain pool or partially restored database.

## Failed disk

1. Confirm the failed member with `zpool status -P tank` and the recorded by-id inventory.
2. Confirm that no second member is degraded or unavailable.
3. Replace the disk with one at least as large as the recorded minimum in the [`zpool replace` contract](https://openzfs.github.io/openzfs-docs/man/master/8/zpool-replace.8.html).
4. Use the stable by-id path when attaching the replacement.
5. Start or confirm the ZFS replacement and resilver operation.
6. Limit workload according to the recorded resilver policy.
7. Monitor `zpool status tank` until resilver completion.
8. Run a scrub after replacement if the site policy requires it.
9. Confirm pool health, application health, backup freshness, and alert delivery.
10. Update the disk inventory and incident record.

Escalate to host recovery if another RAIDZ1 member becomes unavailable before resilver completes.

## Failed host

1. Preserve failed boot media and pool disks without writing to them.
2. Build a compatible host with OpenZFS userland and kernel modules version 2.3 or newer.
3. Restore the repository revision and non-secret configuration.
4. Restore the Vault password and encrypted secrets through the offline process.
5. Restore `/etc/zfs/keys/tank-secure.key` as root-owned mode `0600`.
6. Attach disks using the recorded controller and by-id mapping.
7. Inspect the import with `zpool import` before importing `tank`.
8. Import the existing pool without creating a new pool.
9. Load the encrypted dataset key and verify expected mountpoints.
10. Restore k0s control-plane state with the matching k0s release.
11. Bind local PVs to the replacement node identity and verified dataset paths.
12. Follow the dependencies in the [service catalog](../ansible/service_catalog.yml).
13. Start PostgreSQL and verify recovery before its clients.
14. Start Meilisearch and Manticore and verify their storage.
15. Start the AFFiNE Redis workload and verify it before AFFiNE.
16. Start Stalwart, Grist, AFFiNE, Zabbix, and other database-backed applications.
17. Start OnlyOffice, Tika, and Bleve and verify them before OpenCloud.
18. Start OpenCloud and remaining independent workloads.
19. Run internal and external acceptance checks.
20. Confirm a new independent backup before closing recovery.

Never authorize `zpool create` when recovering an existing pool.

Use import flags such as forced import only after verifying that no other host has the pool imported.

## Lost pool

1. Build the replacement host from the recorded baseline.
2. Create replacement storage only after confirming the original pool is unrecoverable or safely isolated.
3. Restore the encrypted dataset hierarchy and quotas.
4. Restore the coordinated PostgreSQL and application-file recovery point.
5. Restore k0s control-plane state separately.
6. Rebind local PVs to the restored paths and node identity.
7. Follow the failed-host startup order.
8. Rebuild disposable indexes from authoritative sources.
9. Complete all external acceptance checks.

## Failed migration or upgrade

1. Stop the upgraded workload and every writer to its affected data.
2. Preserve logs and the failed state for diagnosis.
3. Decide whether the documented migration supports forward repair.
4. Restore the pre-change PostgreSQL and application-file recovery point when rollback is required.
5. Restore the prior manifests, images, configuration, and secrets.
6. Start PostgreSQL before the application.
7. Verify schema, extension, and application versions.
8. Run service-specific and external acceptance checks.
9. Keep the failed recovery point until the incident review is complete.

Never start an older application image against a schema whose backward compatibility is unknown.

## Restore exercise

1. Use an isolated host or isolated network and storage names.
2. Retrieve recovery data through the same custody process used for an incident.
3. Verify backup integrity before restoration.
4. Restore k0s and application data through their separate procedures.
5. Measure data loss against the recorded RPO.
6. Measure service restoration against the recorded RTO.
7. Run database, mail, application, and office-save acceptance checks.
8. Record missing credentials, artifacts, instructions, and dependencies.
9. Correct the recovery material and repeat failed checks.
10. Record the successful exercise time and recovery-point identifier.
