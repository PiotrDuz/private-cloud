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
        - Tuning primarycache: ram limits aggressive, so primarycache=all, shared_buffers=25% of user-provided maximum postgres container memory
        Postgres side:
        - Setting full_page_writes=off
        - Disable postgres checksumming
        - Disable Postgres compression
        - Tune wal_init_zero & wal_recycle
        - Setting logbias=latency (instead of logbias=throughput)
    3. postgres service with its own kubernetess volume linked with dataset is deployed in k0s
    4. Install, enable, and verify pgvector in the shared PostgreSQL service
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
5. Setup MEILISEARCH
    1. Create a Meilisearch dataset under tank/secure/backup/k0s/services/meilisearch with a quota
    2. Deploy Meilisearch in k0s with its own 10Ti PV
6. Setup STALWART email
    1. Deploy Stalwart with its own dataset under tank/secure/backup/k0s/services/stalwart, 10Ti PV, and quota
    2. Create a Stalwart database, login role, and credentials Secret in the existing postgres service
    3. Configure the data store to use the Stalwart postgres database
    4. Configure the blob store as filesystem storage on the Stalwart PV
    5. Configure the search store to use Meilisearch
    6. Configure the Default in-memory store to use the postgres data store
    7. Configure Stalwart as the authoritative mailbox and submission service for the user-provided domain
    8. Expose a public mail subdomain with SMTP, IMAPS, authenticated submission, and valid TLS
    9. Configure the Gmail mobile client to use Stalwart IMAPS and SMTP submission
    10. Map forwarding-subdomain recipients to primary-domain Stalwart accounts
    11. Store inbox.eu credentials in a Secret and relay non-local outbound mail through its SMTP service over TLS
    12. Verify client access, local delivery, external delivery, and inbound redirects
7. Setup APACHE TIKA
    1. Create an Apache Tika dataset under tank/secure/backup/k0s/services/tika with a quota
    2. Deploy Apache Tika in k0s with its own 10Ti PV
8. Setup BLEVE
    1. Create a Bleve dataset under tank/secure/backup/k0s/services/bleve with a quota
    2. Create a dedicated 10Ti PV for the embedded OpenCloud Bleve search backend
9. Setup ONLYOFFICE
    1. Create an OnlyOffice dataset under tank/secure/backup/k0s/services/onlyoffice with a quota
    2. Deploy OnlyOffice Community Edition in k0s with its own 10Ti PV
    3. Enable the OnlyOffice WOPI integration
    4. Expose OnlyOffice for the user-provided domain through a valid TLS reverse proxy
10. Setup OPENCLOUD
    1. Deploy OpenCloud with its own dataset under tank/secure/backup/k0s/services/opencloud, 10Ti PV, and quota
    2. Configure OpenCloud to use Apache Tika for content extraction
    3. Configure the search service to use the Bleve backend
    4. Configure supported cache stores to use in-memory storage
    5. Configure the file storage to use filesystem storage on the OpenCloud PV
    6. Enable the built-in collaboration service and connect it to OnlyOffice
    7. Install and configure the Draw.io web extension
    8. Expose OpenCloud for the user-provided domain through a valid TLS reverse proxy
11. Setup GRIST
    1. Deploy Grist with its own dataset under tank/secure/backup/k0s/services/grist, 10Ti PV, and quota
    2. Create a Grist database, login role, and credentials Secret in the existing postgres service
    3. Persist Grist documents on its PV and isolate formulas with Pyodide
    4. Expose Grist for the user-provided domain through a valid TLS reverse proxy
12. Setup MANTICORE SEARCH
    1. Create a Manticore Search dataset under tank/secure/backup/k0s/services/manticore with a quota
    2. Deploy Manticore Search in k0s with its own 10Ti PV
13. Setup AFFINE
    1. Deploy AFFiNE with its own dataset under tank/secure/backup/k0s/services/affine, 10Ti PV, and quota
    2. Create an AFFiNE database with pgvector enabled in the shared PostgreSQL service
    3. Configure the server-side indexer to use Manticore Search
    4. Deploy Redis and a versioned migration Job
    5. Persist AFFiNE blobs and configuration on its PV
    6. Expose AFFiNE for the user-provided domain through a valid TLS reverse proxy
