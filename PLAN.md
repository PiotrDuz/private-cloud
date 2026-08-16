1. ZFS install (folder zfs)
    1. Setup disks into raidz1, root = "tank"
    2. Setup encryption, use file with known password so it can be recreated once file is lost.
    "tank/secure"
    3. Give tank/secure all available pool capacity without a quota or reservation
    4. Create tank/secure/backup and tank/secure/no-backup datasets
    5. Schedule monthly scrubs
    6. Enable auto trims
    7. add auto mount on system startup service
2. Setup k0s (fodler k0s)
    1. place container images under tank/secure/no-backup/k0s/images
    2. place ephemeral kubelet data under tank/secure/no-backup/k0s/ephemeral
    3. place k0s setup and configuration under tank/secure/backup/k0s/config
    4. Each current service creates its own dataset under tank/secure/backup/k0s/services
    5. install k0s
    6. make sure k0s starts after zfs is muounted and unlocked on system startup
    7. Set explicit quotas for config, images, and ephemeral leaf datasets
3. Setup postgres service (in k0s-services parent folder)
    1. create postgres zfs dataset under tank/secure/backup/k0s/services/postgres
    2. Tune dataset and postgres config. Use URL as a reference, but implement only featured mentioned below: https://vadosware.io/post/everything-ive-seen-on-optimizing-postgres-on-zfs-on-linux/#tuning-shared_buffers
        - Setting recordsize to 8k
        - Enable compression
        - Reducing read-ahead
        - Tuning primarycache: ram limits aggressive, so primarycache=all, shared_buffers= user provided postgres max ram + 50%
        Postgres side:
        - Setting full_page_writes=off
        - Disable postgres checksumming
        - Disable Postgres compression
        - Tune wal_init_zero & wal_recycle
        - Setting logbias=latency (instead of logbias=throughput)
    3. postgres service with its own kubernetess volume linked with dataset is deployed in k0s
4. Setup ZABBIX
    1. Run zabbix metrics gatherer on host (install, make sure it starts with system)
        - zfs errors
        - scrubs run
        - fixed leaf dataset size, quota, and quota utilization
        - total pool size
        - SMART disk metrics
        - system general performance (ram, cpu)
        - RAM ECC corrected and uncorrected errors
        - old snapshots, large snapshots
    2. Zabbix server with its owndataset and PV should be deployed in cluster
    3. Zabbix service creates its database, login role, and credentials Secret
    4. Connect zabbix to database
    5. expose zabbix server port so it can be connected with metrics gatherer on host
    6. WARNINGS:
        - Warn when tank usage exceeds 80% and raise a high alert above 90%
        - Raise a high alert when a fixed leaf dataset reaches 90% of its quota
        - alert on SMART disk low health
        - alert on unfixed zfs error
        - warning on zfs error that has been fixed (scrub or normal operation)
        - alert on unfixed ECC error
        - warning on ECC error that has been fixed
5. Setup 
5. Setup STALWART email
    1. another kubernetess service, own dataset under tank/secure/backup/k0s/services and PV
    
