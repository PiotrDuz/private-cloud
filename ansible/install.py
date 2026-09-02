#!/usr/bin/env python3
"""Interactive configuration lifecycle for the private-cloud Ansible playbook."""

from __future__ import annotations

import fcntl
import os
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from install_helpers import (
    ANSIBLE_CONFIG,
    EXAMPLE_CONFIGURATION,
    INVENTORY,
    KUBECONFIG_FILE,
    LOCK_FILE,
    MODES,
    OLD_VAULT_PASSWORD_FILE,
    PLAYBOOK,
    POOL_NAME,
    PUBLIC_CONFIGURATION,
    RUNTIME_DIRECTORY,
    SECRETS_CONFIGURATION,
    SECRET_SCHEMAS,
    SECRET_STAGES,
    TEMP_PUBLIC_FILE,
    TEMP_RUNTIME_FILE,
    TEMP_SECRET_FILE,
    VAULT_PASSWORD_FILE,
    InstallerError,
    atomic_write,
    decrypt_secrets,
    dump_yaml,
    encrypt_secrets,
    ensure_runtime_directory,
    load_yaml,
    migrate_public_configuration,
    migrate_secrets_configuration,
    pool_exists,
    prompt_choice,
    prompt_int,
    prompt_line,
    prompt_secret,
    redact_secrets,
    rekey_secrets,
    remove_stale_runtime_files,
    require_interactive_terminal,
    require_commands,
    require_kubernetes_readiness,
    require_root,
    run_command,
    validate_public_configuration,
    validate_secrets_configuration,
    validate_vault_ciphertext,
    write_password_file,
    write_secret_file,
)


def main() -> int:
    try:
        result = run_installation()
    except (InstallerError, KeyboardInterrupt) as error:
        if isinstance(error, KeyboardInterrupt):
            print("Installation cancelled.", file=sys.stderr)
        else:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(dump_yaml(result).rstrip())
    return 0


def run_installation() -> dict[str, Any]:
    require_root()
    require_interactive_terminal(sys.stdin, sys.stdout)
    ensure_runtime_directory()
    with installer_lock(), runtime_cleanup():
        remove_stale_runtime_files()
        require_commands(["ansible-playbook", "ansible-vault"])
        require_kubernetes_readiness()
        stored_public = load_yaml(PUBLIC_CONFIGURATION) if PUBLIC_CONFIGURATION.is_file() else None
        existing_public = None
        if stored_public is not None:
            existing_public = migrate_public_configuration(stored_public, default_public_configuration())
            resolve_affine_indexer_migration(stored_public, existing_public)
            validate_public_configuration(existing_public)
        mode = choose_mode(existing_public is not None)
        if mode == "create" and existing_public is not None:
            raise InstallerError("A public configuration already exists; choose update, reapply, or rotate")
        if mode == "create" and pool_exists():
            raise InstallerError("An existing tank pool cannot be adopted during initial migration")
        if mode == "create":
            require_commands(["lsblk"])
        if mode in {"update", "reapply", "rotate"} and existing_public is None:
            raise InstallerError("An existing public configuration is required for this lifecycle")
        public = collect_valid_public_configuration(existing_public, mode)
        stages = public["private_cloud"]["stages"]

        old_password: str | None = None
        original_secrets: dict[str, Any] | None = None
        if mode != "create":
            if not SECRETS_CONFIGURATION.is_file():
                raise InstallerError("The encrypted secrets configuration is missing")
            validate_vault_ciphertext(SECRETS_CONFIGURATION)
            old_password = prompt_secret("Current Ansible Vault password", confirm=False)
            write_password_file(old_password)
            write_password_file(old_password, OLD_VAULT_PASSWORD_FILE)
            decrypt_secrets(SECRETS_CONFIGURATION, TEMP_SECRET_FILE, VAULT_PASSWORD_FILE)
            stored_secrets = load_yaml(TEMP_SECRET_FILE)
            original_secrets = _copy_mapping(stored_secrets)
            secrets_configuration = migrate_secrets_configuration(stored_secrets)
        else:
            secrets_configuration = {"secrets_schema_version": 1, "private_cloud_secrets": {}}

        secrets_configuration = collect_missing_secrets(secrets_configuration, public)
        validate_secrets_configuration(secrets_configuration, stages)

        if mode in {"rotate", "update"}:
            secrets_configuration = collect_valid_changed_secrets(secrets_configuration, public, mode)
        if original_secrets is not None:
            reject_unsupported_secret_rotations(original_secrets, secrets_configuration)

        public_changed = stored_public is None or public != stored_public
        secrets_changed = original_secrets is None or secrets_configuration != original_secrets
        if not secrets_changed:
            TEMP_SECRET_FILE.unlink(missing_ok=True)

        vault_password = old_password or prompt_secret("Ansible Vault password")
        vault_password_changed = mode in {"update", "rotate"} and prompt_bool_for_vault_change()
        if vault_password_changed:
            new_password = prompt_secret("New Ansible Vault password")
        else:
            new_password = vault_password
        write_password_file(new_password)

        print(dump_yaml(redact_secrets({**public, **secrets_configuration})).rstrip())
        runtime = build_runtime_values(public, mode)
        atomic_write(TEMP_RUNTIME_FILE, dump_yaml(runtime), 0o600)
        if not prompt_bool("Allow Ansible to start", True):
            raise InstallerError("Ansible run was not confirmed")
        if public_changed:
            atomic_write(TEMP_PUBLIC_FILE, dump_yaml(public), 0o600)
        if secrets_changed:
            write_secret_file(secrets_configuration, stages)
            encrypt_secrets(TEMP_SECRET_FILE, SECRETS_CONFIGURATION, VAULT_PASSWORD_FILE)
        elif vault_password_changed:
            rekey_secrets(SECRETS_CONFIGURATION, OLD_VAULT_PASSWORD_FILE, VAULT_PASSWORD_FILE)
        if public_changed:
            atomic_write(PUBLIC_CONFIGURATION, dump_yaml(public), 0o640)
        run_playbook()
        return {"status": "completed", "mode": mode, "playbook": str(PLAYBOOK)}


@contextmanager
def installer_lock() -> Iterator[None]:
    if LOCK_FILE.is_symlink():
        raise InstallerError(f"Unsafe symbolic-link lock file: {LOCK_FILE}")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(LOCK_FILE, flags, 0o600)
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or stat.S_IMODE(details.st_mode) != 0o600:
        os.close(descriptor)
        raise InstallerError("Installer lock must be a root-owned regular file with mode 0600")
    with os.fdopen(descriptor, "r+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstallerError("Another installer session is already running") from error
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def runtime_cleanup() -> Iterator[None]:
    try:
        yield
    finally:
        for path in (TEMP_SECRET_FILE, TEMP_PUBLIC_FILE, TEMP_RUNTIME_FILE, VAULT_PASSWORD_FILE, OLD_VAULT_PASSWORD_FILE, KUBECONFIG_FILE):
            path.unlink(missing_ok=True)


def choose_mode(has_public: bool) -> str:
    default = "reapply" if has_public else "create"
    return prompt_choice("Configuration action", MODES, default)


def resolve_affine_indexer_migration(stored: dict[str, Any], migrated: dict[str, Any]) -> None:
    if stored.get("schema_version", 0) >= 2 or not migrated["private_cloud"]["stages"]["affine"]:
        return
    choice = prompt_choice(
        "AFFiNE now requires Manticore (enable-manticore/disable-affine/cancel)",
        ("enable-manticore", "disable-affine", "cancel"),
        "cancel",
    )
    if choice == "enable-manticore":
        migrated["private_cloud"]["stages"]["manticore"] = True
    elif choice == "disable-affine":
        migrated["private_cloud"]["stages"]["affine"] = False
    else:
        raise InstallerError("Configuration migration cancelled; no changes made")


def collect_public_configuration(existing: dict[str, Any] | None, mode: str) -> dict[str, Any]:
    if existing is not None and mode in {"reapply", "rotate"}:
        return existing
    source = existing or default_public_configuration()
    if mode == "update":
        sections = prompt_line("Sections to change (stages, storage, k0s, postgres, meilisearch, tika, bleve, onlyoffice, opencloud, grist, manticore, affine, stalwart, zabbix)", "").split()
    else:
        sections = ["stages", "storage", "k0s", "postgres", "meilisearch", "tika", "bleve", "onlyoffice", "opencloud", "grist", "manticore", "affine", "stalwart", "zabbix"]
    result = _copy_mapping(source)
    stages = result["private_cloud"]["stages"]
    if "stages" in sections:
        for stage in stages:
            stages[stage] = prompt_bool(f"Enable {stage}", stages[stage])
    cloud = result["private_cloud"]
    if "storage" in sections and cloud["stages"]["zfs"]:
        if mode == "create":
            discover_disks()
        existing_disks = [] if mode == "create" else cloud["storage"]["disks"]
        cloud["storage"]["disks"] = prompt_disks(existing_disks)
    if "k0s" in sections:
        for key in ("version", "sha256", "config_quota", "images_quota", "ephemeral_quota"):
            cloud["k0s"][key] = prompt_line(f"k0s {key}", cloud["k0s"][key])
    if "postgres" in sections:
        for key in ("volume_size", "max_ram"):
            cloud["postgres"][key] = prompt_line(f"PostgreSQL {key}", cloud["postgres"][key])
    if "meilisearch" in sections:
        for key in ("storage_size", "max_ram"):
            cloud["meilisearch"][key] = prompt_line(f"Meilisearch {key}", cloud["meilisearch"][key])
    if "tika" in sections:
        for key in ("storage_size", "max_ram"):
            cloud["tika"][key] = prompt_line(f"Tika {key}", cloud["tika"][key])
    if "bleve" in sections:
        cloud["bleve"]["storage_size"] = prompt_line("Bleve storage_size", cloud["bleve"]["storage_size"])
    if "onlyoffice" in sections:
        for key in ("storage_size", "max_ram", "hostname"):
            cloud["onlyoffice"][key] = prompt_line(f"OnlyOffice {key}", cloud["onlyoffice"][key])
        cloud["onlyoffice"]["node_port"] = prompt_int("OnlyOffice node_port", cloud["onlyoffice"]["node_port"])
    if "opencloud" in sections:
        for key in ("storage_size", "max_ram", "hostname"):
            cloud["opencloud"][key] = prompt_line(f"OpenCloud {key}", cloud["opencloud"][key])
        cloud["opencloud"]["node_port"] = prompt_int("OpenCloud node_port", cloud["opencloud"]["node_port"])
    if "grist" in sections:
        for key in ("storage_size", "max_ram", "database_name", "database_username", "default_email", "hostname"):
            cloud["grist"][key] = prompt_line(f"Grist {key}", cloud["grist"][key])
        cloud["grist"]["node_port"] = prompt_int("Grist node_port", cloud["grist"]["node_port"])
    if "manticore" in sections:
        for key in ("storage_size", "max_ram"):
            cloud["manticore"][key] = prompt_line(f"Manticore {key}", cloud["manticore"][key])
    if "affine" in sections:
        for key in ("storage_size", "max_ram", "redis_max_ram", "database_name", "database_username", "hostname"):
            cloud["affine"][key] = prompt_line(f"AFFiNE {key}", cloud["affine"][key])
        cloud["affine"]["node_port"] = prompt_int("AFFiNE node_port", cloud["affine"]["node_port"])
    if "stalwart" in sections:
        for key in ("storage_size", "max_ram", "database_name", "database_username", "domain", "forwarding_domain", "hostname", "acme_contact", "admin_username", "mailbox_username", "relay_host", "relay_username"):
            cloud["stalwart"][key] = prompt_line(f"Stalwart {key}", cloud["stalwart"][key])
        cloud["stalwart"]["relay_port"] = prompt_int("Stalwart relay_port", cloud["stalwart"]["relay_port"])
        cloud["stalwart"]["relay_implicit_tls"] = prompt_bool("Stalwart relay_implicit_tls", cloud["stalwart"]["relay_implicit_tls"])
        for key in ("https_node_port", "smtp_node_port", "submissions_node_port", "submission_node_port", "imaps_node_port"):
            cloud["stalwart"][key] = prompt_int(f"Stalwart {key}", cloud["stalwart"][key])
    if "zabbix" in sections:
        for key in ("storage_size", "database_name", "database_username", "hostname", "admin_username", "agent_server_active"):
            cloud["zabbix"][key] = prompt_line(f"Zabbix {key}", cloud["zabbix"][key])
        for key in ("server_node_port", "web_node_port"):
            cloud["zabbix"][key] = prompt_int(f"Zabbix {key}", cloud["zabbix"][key])
    return result


def collect_valid_public_configuration(existing: dict[str, Any] | None, mode: str) -> dict[str, Any]:
    while True:
        candidate = collect_public_configuration(existing, mode)
        try:
            validate_public_configuration(candidate)
            return candidate
        except InstallerError as error:
            print(f"Invalid configuration: {error}", file=sys.stderr)


def collect_valid_changed_secrets(configuration: dict[str, Any], public: dict[str, Any], mode: str) -> dict[str, Any]:
    stages = public["private_cloud"]["stages"]
    while True:
        candidate = rotate_secrets(configuration, stages) if mode == "rotate" else update_secrets(configuration, stages)
        try:
            validate_secrets_configuration(candidate, stages)
            return candidate
        except InstallerError as error:
            print(f"Invalid secret configuration: {error}", file=sys.stderr)


def default_public_configuration() -> dict[str, Any]:
    if EXAMPLE_CONFIGURATION.is_file():
        return load_yaml(EXAMPLE_CONFIGURATION)
    raise InstallerError(f"Missing example configuration: {EXAMPLE_CONFIGURATION}")


def collect_missing_secrets(configuration: dict[str, Any], public: dict[str, Any]) -> dict[str, Any]:
    result = _copy_mapping(configuration)
    secrets_root = result["private_cloud_secrets"]
    stages = public["private_cloud"]["stages"]
    prompts = {
        ("storage", "encryption_passphrase"): "ZFS encryption passphrase",
        ("postgres", "admin_password"): "PostgreSQL administrator password",
        ("meilisearch", "master_key"): "Meilisearch master key",
        ("onlyoffice", "jwt_secret"): "OnlyOffice JWT secret",
        ("opencloud", "admin_password"): "OpenCloud administrator password",
        ("grist", "database_password"): "Grist database password",
        ("grist", "session_secret"): "Grist session secret",
        ("grist", "boot_key"): "Grist boot key",
        ("affine", "database_password"): "AFFiNE database password",
        ("stalwart", "database_password"): "Stalwart database password",
        ("stalwart", "admin_password"): "Stalwart administrator password",
        ("stalwart", "mailbox_password"): "Stalwart mailbox password",
        ("stalwart", "relay_password"): "inbox.eu SMTP password",
        ("zabbix", "database_password"): "Zabbix database password",
        ("zabbix", "admin_password"): "Zabbix administrator password",
    }
    for section, keys in SECRET_SCHEMAS.items():
        if not stages[SECRET_STAGES[section]]:
            continue
        section_values = secrets_root.setdefault(section, {})
        for key in sorted(keys):
            if key not in section_values:
                section_values[key] = prompt_secret(prompts[(section, key)])
    return result


def update_secrets(configuration: dict[str, Any], stages: dict[str, bool]) -> dict[str, Any]:
    result = _copy_mapping(configuration)
    for section, key in (
        ("meilisearch", "master_key"),
        ("stalwart", "database_password"),
        ("stalwart", "admin_password"),
        ("stalwart", "mailbox_password"),
        ("stalwart", "relay_password"),
        ("onlyoffice", "jwt_secret"),
        ("grist", "database_password"),
        ("grist", "session_secret"),
        ("grist", "boot_key"),
        ("affine", "database_password"),
        ("zabbix", "database_password"),
    ):
        if stages[SECRET_STAGES[section]] and prompt_bool(f"Change {section}.{key}", False):
            result["private_cloud_secrets"][section][key] = prompt_secret(f"New {section}.{key}")
    return result


def rotate_secrets(configuration: dict[str, Any], stages: dict[str, bool]) -> dict[str, Any]:
    result = _copy_mapping(configuration)
    selected = prompt_line("Secrets to rotate (meilisearch stalwart_database stalwart_admin mailbox relay onlyoffice grist_database grist_session grist_boot affine_database zabbix_database)", "all").split()
    supported = {"all", "meilisearch", "stalwart_database", "stalwart_admin", "mailbox", "relay", "onlyoffice", "grist_database", "grist_session", "grist_boot", "affine_database", "zabbix_database"}
    if set(selected) - supported:
        raise InstallerError("Unsupported credential rotation requested")
    if "all" in selected:
        selected = ["meilisearch", "stalwart_database", "stalwart_admin", "mailbox", "relay", "onlyoffice", "grist_database", "grist_session", "grist_boot", "affine_database", "zabbix_database"]
    mapping = {
        "meilisearch": ("meilisearch", "master_key"),
        "stalwart_database": ("stalwart", "database_password"),
        "stalwart_admin": ("stalwart", "admin_password"),
        "mailbox": ("stalwart", "mailbox_password"),
        "relay": ("stalwart", "relay_password"),
        "zabbix_database": ("zabbix", "database_password"),
        "onlyoffice": ("onlyoffice", "jwt_secret"),
        "grist_database": ("grist", "database_password"),
        "grist_session": ("grist", "session_secret"),
        "grist_boot": ("grist", "boot_key"),
        "affine_database": ("affine", "database_password"),
    }
    for name in selected:
        if name in mapping:
            section, key = mapping[name]
            if stages[SECRET_STAGES[section]]:
                result["private_cloud_secrets"][section][key] = prompt_secret(f"New {section}.{key}")
    return result


def reject_unsupported_secret_rotations(previous: dict[str, Any], candidate: dict[str, Any]) -> None:
    unsupported = (
        ("storage", "encryption_passphrase"),
        ("postgres", "admin_password"),
        ("zabbix", "admin_password"),
    )
    changed = [
        f"{section}.{key}"
        for section, key in unsupported
        if key in previous.get("private_cloud_secrets", {}).get(section, {})
        and previous["private_cloud_secrets"][section][key] != candidate["private_cloud_secrets"][section][key]
    ]
    if changed:
        raise InstallerError(f"Unsupported credential rotation requested: {', '.join(changed)}")


def configured_secret_markers() -> dict[str, Any]:
    return {
        "storage": {"encryption_passphrase": "configured"},
        "postgres": {"admin_password": "configured"},
        "meilisearch": {"master_key": "configured"},
        "stalwart": {"database_password": "configured", "admin_password": "configured", "mailbox_password": "configured", "relay_password": "configured"},
        "onlyoffice": {"jwt_secret": "configured"},
        "opencloud": {"admin_password": "configured"},
        "grist": {"database_password": "configured", "session_secret": "configured", "boot_key": "configured"},
        "affine": {"database_password": "configured"},
        "zabbix": {"database_password": "configured", "admin_password": "configured"},
    }


def prompt_bool(prompt: str, default: bool) -> bool:
    answer = prompt_line(prompt, "yes" if default else "no").strip().lower()
    while answer not in {"yes", "no", "y", "n"}:
        answer = prompt_line(prompt, "yes" if default else "no").strip().lower()
    return answer in {"yes", "y"}


def prompt_bool_for_vault_change() -> bool:
    return prompt_bool("Change the Ansible Vault password", False)


def discover_disks() -> list[str]:
    result = run_command(["lsblk", "--json", "--bytes", "--paths", "--output", "PATH,TYPE,SIZE,MODEL"]).stdout
    try:
        devices = __import__("json").loads(result).get("blockdevices", [])
    except ValueError as error:
        raise InstallerError("lsblk returned invalid JSON") from error
    paths = []
    for device in devices:
        path = str(device.get("path", ""))
        if device.get("type") == "disk":
            stable = stable_disk_id(path)
            if stable:
                print(f"{stable} ({device.get('model') or 'unknown'}, {device.get('size') or 0} bytes)")
                paths.append(stable)
    if len(paths) < 2:
        raise InstallerError("RAIDZ1 needs at least two stable whole disks")
    return paths


def stable_disk_id(path: str) -> str | None:
    directory = Path("/dev/disk/by-id")
    if not directory.is_dir():
        return None
    target = Path(os.path.realpath(path))
    choices = [entry for entry in directory.iterdir() if entry.is_symlink() and "-part" not in entry.name and Path(os.path.realpath(entry)) == target]
    return str(sorted(choices, key=lambda item: item.name)[0]) if choices else None


def prompt_disks(existing: list[str]) -> list[str]:
    default = " ".join(existing) if existing else None
    value = prompt_line("Stable disk IDs separated by spaces", default)
    return value.split()


def build_runtime_values(public: dict[str, Any], mode: str) -> dict[str, Any]:
    runtime: dict[str, Any] = {"private_cloud_runtime": {"initial_install": False}}
    if public["private_cloud"]["stages"]["zfs"] and not pool_exists():
        require_commands(["lsblk"])
        confirmation = prompt_line(f"Type CREATE {POOL_NAME} to approve disk erasure")
        if confirmation != f"CREATE {POOL_NAME}":
            raise InstallerError("Confirmation did not match; no changes made")
        runtime["private_cloud_runtime"].update({"initial_install": True, "storage_create_confirmation": confirmation})
    return runtime


def run_playbook() -> None:
    run_command([
        "ansible-playbook",
        "-i", str(INVENTORY),
        str(PLAYBOOK),
        "--extra-vars", f"@{PUBLIC_CONFIGURATION}",
        "--extra-vars", f"@{SECRETS_CONFIGURATION}",
        "--extra-vars", f"@{TEMP_RUNTIME_FILE}",
        "--vault-password-file", str(VAULT_PASSWORD_FILE),
    ], environment={"ANSIBLE_CONFIG": str(ANSIBLE_CONFIG)}, stage="ansible-playbook")


def _copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    import copy
    return copy.deepcopy(value)


if __name__ == "__main__":
    raise SystemExit(main())
