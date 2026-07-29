# Interactive Python setup

This app runs the repository installers in dependency order.

## Stages

1. ZFS storage.
2. k0s cluster.
3. PostgreSQL service.
4. Zabbix Kubernetes service.
5. Zabbix host agent.

Each stage requests an action and its required configuration.
The flow stops when an installer fails.
Skipped stages support resuming an existing installation.

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
The PostgreSQL password is passed only in the child process environment.
The ZFS installer still requires its destructive `CREATE tank` confirmation.
