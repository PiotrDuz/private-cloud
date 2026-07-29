1. ZFS install (folder zfs)
    1. Setup disks into raidz1, root = "tank"
    2. Setup encryption, use file with known password so it can be recreated once file is lost. 
    "tank/secure"
    3. Schedule monthly scrubs
    4. Enable auto trims
    5. add auto mount on system startup service
2. Setup k0s (fodler k0s)
    1. place container data and images under tank/secure/k0s/images, tank/secure/k0s/ephemeral for containers
    2. place k0s setup and configuration under tank/secure/k0s/config, 
    tank/secure/k8s/volumes for persistent application volume
    3. Further datasets for each service that should be backed up is be placed in k0s/services-backed
    4. Further datasets for servcies not to be backed up places in k0s/services-no-backup
    5. install k0s
    6. make sure k0s starts after zfs is muounted and unlocked on system startup
3. Setup postgres service (in k0s-services parent folder)
    1. create postgres zfs dataset under k0s/services-backed/postgres
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
        - datasets size
        - total pool size
        - SMART disk metrics
        - system general performance (ram, cpu)
    2. Zabbix server with its owndataset and PV should be deployed in cluster
    3. Postgres should have zabbix database created
    4. Connect zabbix to database
    5. expose zabbix server port so it can be connected with metrics gatherer on host
    