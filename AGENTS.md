# Private cloud repository instructions

## Repo facts

- Single host: OpenZFS pool `tank` plus one k0s cluster; state lives under `/tank/secure`.
- `ansible/install.py` is the only supported entrypoint; it collects configuration and runs `ansible/site.yml` roles in fixed order.
- `PLAN.md` is target state, `TODO.md` is outstanding work; do not treat planned work as implemented.
- Greenfield project: no migrations or compatibility paths.

## Commands

- Install collections: `sudo ansible-galaxy collection install -r ansible/requirements.yml`
- Install or reapply: `sudo python3 ansible/install.py`; requires root, an interactive TTY, PyYAML, and the Python Kubernetes client.
- Modes: `create`, `update`, `reapply`, `rotate`; only `create` erases disks and requires typing `CREATE tank`.
- Debian hosts must disable the `zabbix_agent` stage; use Ubuntu for all stages.
- No tests, linter, or CI. Verification is the playbook's preflight and verify tasks on a live host, so changes cannot be fully validated locally.
- Do not run `ansible-playbook` directly; the installer writes runtime values and the Vault password under `/run/private-cloud`.

## Configuration contract

- Public state: `ansible/config/private-cloud.yml`; Vault ciphertext: `ansible/config/private-cloud.secrets.yml`; `ansible/config/private-cloud.example.yml` mirrors `validate_public_configuration`.
- Keep plaintext secrets out of the repo; they live only in the Vault ciphertext file.
- Bump every schema site together: `CURRENT_SCHEMA_VERSION` and `CURRENT_SECRETS_SCHEMA_VERSION` in `ansible/install_helpers.py`, the asserts in `ansible/roles/preflight/tasks/main.yml`, and the example file.
- Adding a stage touches `ansible/install.py` prompts, `ansible/install_helpers.py`, preflight asserts, the example config, `ansible/service_catalog.yml`, and `ansible/site.yml`.
- `ansible/service_catalog.yml` also owns the stage dependency chain and the Zabbix dataset inventory; preflight validates both.

## Layout

- `ansible/roles/<stage>/` one role per installer stage; `ansible/tasks/*.yml` holds shared snippets such as `render_manifests.yml` and `service_dataset*.yml`.
- `k0s-services/<service>/templates/*.yaml.j2` is the source of truth for Kubernetes resources; see `k0s-services/AGENTS.md`.
- `logging/`, `media/`, and `zabbix/` hold Python scripts that roles copy to the host or run during the play.
- Namespaces: `private-cloud`, `media`, `edge`, `network-access`, `dns-system`, `observability`, `kube-system`.
- Operate with `sudo k0s kubectl ...` and `sudo journalctl -u k0scontroller.service`; kubeconfig is `/run/private-cloud/kubeconfig`.

## Writing documentation rules

- In lists and bullet points, use single, short sentences to show intent; avoid additional explanations.

## Writing scripts rules

1. Do not write usage echo; documentation lives elsewhere and the script stays lean.
2. Do not write tests.
3. Do not write dry-runs; run only requested functionality.
4. Use Python for scripts.
5. Place helpers in separate files; move helpers shared by folders to the top level.
6. Top-level methods handle main logic; less important methods and class definitions go at the bottom. The top method is procedural and shows the flow.
7. Do not add excessive prints; scripts self-check and return a result for the parent script that runs them in order.

## Kubernetes service rules

- Give each service its own dataset under `backup/k0s/services` or `no-backup/k0s/services`; backup is the default.
- Give each service a dedicated 10Ti PV so it does not need extension.
- Give each service dataset a quota.
- Follow `k0s-services/AGENTS.md` for manifest, secret, and resource rules.
