# Interactive Python setup

This app runs the repository installers in dependency order.

## Stages

1. ZFS storage.
2. k0s cluster.
3. PostgreSQL service.
4. Zabbix service, template import, and host registration.
5. Zabbix host agent.

Each stage requests an action and its required configuration.
All storage stages use the fixed `tank/secure` root dataset without prompting.
The Zabbix service and agent use the fixed `private-cloud-zabbix` host name.
The k0s stage uses the pinned version without extra prompts.
The ZFS stage gives `tank/secure` all available pool capacity without a size prompt.
Service installers create their own datasets, PVs, and PVCs.
The flow stops when an installer fails.
Skipped stages support resuming an existing installation.

## Saved progress

Progress is stored in `/var/lib/private-cloud/setup-progress.json`.
A stage is completed only after its installer exits successfully.
An interrupted stage remains selected as the resume point.
The file stores non-secret setup values and never stores passwords or passphrases.
The next run prompts to resume or reset the checkpoint.
Reset the checkpoint after dismantling the installation externally.

## Local terminal

Run from the repository root:

```bash
sudo python3 python_setup/setup.py
```

## SSH terminal

Allocate a TTY so prompts and hidden passwords work:

```bash
ssh -t user@server 'cd /path/to/private-cloud && sudo python3 python_setup/setup.py'
```

Use `ssh -tt` if the SSH client does not allocate a TTY with `-t`.
PostgreSQL administrator and Zabbix passwords go only to their child installers.
The ZFS installer still requires its destructive `CREATE tank` confirmation.
