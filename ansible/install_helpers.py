"""Safe input, configuration, and command helpers for the Ansible installer."""

from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO

try:
    import yaml
except ImportError as error:  # pragma: no cover - exercised on an incomplete host
    raise RuntimeError("PyYAML is required to run ansible/install.py") from error


POOL_NAME = "tank"
RUNTIME_DIRECTORY = Path("/run/private-cloud")
PUBLIC_CONFIGURATION = Path(__file__).resolve().parent / "config" / "private-cloud.yml"
SECRETS_CONFIGURATION = Path(__file__).resolve().parent / "config" / "private-cloud.secrets.yml"
EXAMPLE_CONFIGURATION = Path(__file__).resolve().parent / "config" / "private-cloud.example.yml"
INVENTORY = Path(__file__).resolve().parent / "inventory" / "hosts.yml"
PLAYBOOK = Path(__file__).resolve().parent / "site.yml"
LOCK_FILE = RUNTIME_DIRECTORY / "installer.lock"
VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "vault-password"
OLD_VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "old-vault-password"
TEMP_SECRET_FILE = RUNTIME_DIRECTORY / "secrets.yml"
TEMP_PUBLIC_FILE = RUNTIME_DIRECTORY / "public.yml"
TEMP_RUNTIME_FILE = RUNTIME_DIRECTORY / "runtime.yml"
KUBECONFIG_FILE = RUNTIME_DIRECTORY / "kubeconfig"
MODES = ("create", "update", "reapply", "rotate")
QUOTA_PATTERN = re.compile(r"[1-9][0-9]*[KMGTPE]")
RAM_PATTERN = re.compile(r"[1-9][0-9]*(?:Ki|Mi|Gi|Ti)")
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DOMAIN_PATTERN = re.compile(r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
MAILBOX_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._+-]{0,62}[A-Za-z0-9])?")


def require_root() -> None:
    if os.geteuid() != 0:
        raise InstallerError("Run this installer as root")


def require_interactive_terminal(input_stream: TextIO, output_stream: TextIO) -> None:
    if not input_stream.isatty() or not output_stream.isatty():
        raise InstallerError("Run this installer from an interactive terminal")


def ensure_runtime_directory(path: Path = RUNTIME_DIRECTORY) -> None:
    if path.exists() and path.is_symlink():
        raise InstallerError(f"Unsafe symbolic-link runtime directory: {path}")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as error:
        raise InstallerError(f"Runtime directory must be a directory: {path}") from error
    details = path.stat()
    if not stat.S_ISDIR(details.st_mode) or details.st_uid != 0:
        raise InstallerError(f"Runtime directory must be a root-owned directory: {path}")
    if stat.S_IMODE(details.st_mode) != 0o700:
        path.chmod(0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise InstallerError(f"Runtime directory must have mode 0700: {path}")


def remove_stale_runtime_files(path: Path = RUNTIME_DIRECTORY) -> None:
    for name in (TEMP_SECRET_FILE.name, TEMP_PUBLIC_FILE.name, TEMP_RUNTIME_FILE.name, VAULT_PASSWORD_FILE.name, OLD_VAULT_PASSWORD_FILE.name, KUBECONFIG_FILE.name):
        candidate = path / name
        if candidate.exists() or candidate.is_symlink():
            details = candidate.lstat()
            if candidate.is_symlink() or not stat.S_ISREG(details.st_mode):
                raise InstallerError(f"Unsafe non-regular runtime entry: {candidate}")
            if details.st_uid != 0:
                raise InstallerError(f"Runtime entry is not root-owned: {candidate}")
            candidate.unlink()


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        os.chmod(path, mode)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError) as error:
        raise InstallerError(f"Cannot read YAML configuration: {path}") from error
    if not isinstance(value, dict):
        raise InstallerError(f"YAML configuration must contain a mapping: {path}")
    return value


def dump_yaml(value: Mapping[str, Any]) -> str:
    return yaml.safe_dump(value, default_flow_style=False, sort_keys=False)


def prompt_line(prompt: str, default: str | None = None, input_stream: TextIO | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    stream = input_stream or __import__("sys").stdin
    print(f"{prompt}{suffix}: ", end="", flush=True)
    answer = stream.readline()
    if answer == "":
        raise InstallerError("Terminal input ended unexpectedly")
    answer = answer.rstrip("\r\n")
    return default if not answer and default is not None else answer


def prompt_choice(prompt: str, choices: Sequence[str], default: str | None = None) -> str:
    allowed = {choice.lower(): choice for choice in choices}
    while True:
        answer = prompt_line(f"{prompt} ({'/'.join(choices)})", default).strip().lower()
        if answer in allowed:
            return allowed[answer]
        print("Invalid choice.", file=__import__("sys").stderr)


def prompt_bool(prompt: str, default: bool = True) -> bool:
    answer = prompt_line(prompt, "yes" if default else "no").strip().lower()
    while answer not in {"yes", "no", "y", "n"}:
        answer = prompt_line(prompt, "yes" if default else "no").strip().lower()
    return answer in {"yes", "y"}


def prompt_int(prompt: str, default: int) -> int:
    while True:
        value = prompt_line(prompt, str(default)).strip()
        try:
            return int(value)
        except ValueError:
            print("Enter a whole number.", file=__import__("sys").stderr)


def prompt_secret(prompt: str, *, confirm: bool = True) -> str:
    while True:
        value = getpass.getpass(f"{prompt}: ")
        if not value:
            print("Value cannot be empty.", file=__import__("sys").stderr)
            continue
        if confirm:
            second = getpass.getpass("Confirm value: ")
            if not secrets.compare_digest(value, second):
                print("Values do not match.", file=__import__("sys").stderr)
                continue
        return value


def validate_public_configuration(configuration: Mapping[str, Any]) -> None:
    if set(configuration) != {"private_cloud"} or not isinstance(configuration["private_cloud"], dict):
        raise InstallerError("Public configuration must contain only private_cloud")
    cloud = configuration["private_cloud"]
    expected = {"stages", "storage", "k0s", "postgres", "meilisearch", "tika", "bleve", "onlyoffice", "opencloud", "grist", "affine", "stalwart", "zabbix"}
    if set(cloud) != expected:
        raise InstallerError("Public configuration has missing or unknown sections")
    stages = cloud["stages"]
    if not isinstance(stages, dict) or set(stages) != {"zfs", "k0s", "postgres", "meilisearch", "stalwart", "tika", "bleve", "onlyoffice", "opencloud", "grist", "affine", "zabbix_server", "zabbix_agent"}:
        raise InstallerError("Stage configuration is incomplete")
    if any(type(value) is not bool for value in stages.values()):
        raise InstallerError("Every stage flag must be Boolean")
    dependencies = {
        "k0s": ("zfs",),
        "postgres": ("k0s",),
        "meilisearch": ("k0s",),
        "stalwart": ("postgres", "meilisearch"),
        "tika": ("k0s",),
        "bleve": ("k0s",),
        "onlyoffice": ("k0s",),
        "opencloud": ("tika", "bleve", "onlyoffice"),
        "grist": ("postgres",),
        "affine": ("postgres",),
        "zabbix_server": ("postgres",),
        "zabbix_agent": ("zabbix_server",),
    }
    if any(stages[stage] and not all(stages[dependency] for dependency in required) for stage, required in dependencies.items()):
        raise InstallerError("Enabled stages must follow the dependency chain")
    storage = cloud["storage"]
    if not isinstance(storage, dict) or set(storage) != {"disks"}:
        raise InstallerError("Storage configuration has missing or unknown keys")
    disks = storage.get("disks") if isinstance(storage, dict) else None
    if not isinstance(disks, list) or any(not isinstance(disk, str) for disk in disks):
        raise InstallerError("storage.disks must be a list of paths")
    if stages["zfs"]:
        if len(disks) < 2 or len(set(disks)) != len(disks):
            raise InstallerError("At least two unique disks are required for ZFS")
        if any(not re.fullmatch(r"/dev/disk/by-id/[A-Za-z0-9_.:+-]+", disk) for disk in disks):
            raise InstallerError("ZFS disks must use stable /dev/disk/by-id paths")
    k0s = cloud["k0s"]
    if not isinstance(k0s, dict) or set(k0s) != {"version", "config_quota", "images_quota", "ephemeral_quota"}:
        raise InstallerError("k0s configuration has missing or unknown keys")
    for key in ("version", "config_quota", "images_quota", "ephemeral_quota"):
        if not isinstance(k0s, dict) or not isinstance(k0s.get(key), str) or not k0s[key]:
            raise InstallerError(f"Missing k0s.{key}")
    for key in ("config_quota", "images_quota", "ephemeral_quota"):
        if not QUOTA_PATTERN.fullmatch(k0s[key]):
            raise InstallerError(f"Invalid k0s.{key}")
    postgres = cloud["postgres"]
    if not isinstance(postgres, dict) or set(postgres) != {"volume_size", "max_ram"}:
        raise InstallerError("PostgreSQL configuration has missing or unknown keys")
    if not isinstance(postgres, dict) or not QUOTA_PATTERN.fullmatch(str(postgres.get("volume_size", ""))) or not RAM_PATTERN.fullmatch(str(postgres.get("max_ram", ""))):
        raise InstallerError("Invalid PostgreSQL size configuration")
    if ram_to_bytes(postgres["max_ram"]) < 536870912:
        raise InstallerError("PostgreSQL max_ram must be at least 512Mi")
    meilisearch = cloud["meilisearch"]
    if not isinstance(meilisearch, dict) or set(meilisearch) != {"storage_size", "max_ram"}:
        raise InstallerError("Meilisearch configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(meilisearch.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(meilisearch.get("max_ram", ""))):
        raise InstallerError("Invalid Meilisearch size configuration")
    stalwart = cloud["stalwart"]
    tika = cloud["tika"]
    if not isinstance(tika, dict) or set(tika) != {"storage_size", "max_ram"}:
        raise InstallerError("Tika configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(tika.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(tika.get("max_ram", ""))):
        raise InstallerError("Invalid Tika size configuration")
    bleve = cloud["bleve"]
    if not isinstance(bleve, dict) or set(bleve) != {"storage_size"} or not QUOTA_PATTERN.fullmatch(str(bleve.get("storage_size", ""))):
        raise InstallerError("Invalid Bleve storage configuration")
    onlyoffice = cloud["onlyoffice"]
    expected_onlyoffice = {"storage_size", "max_ram", "hostname", "node_port"}
    if not isinstance(onlyoffice, dict) or set(onlyoffice) != expected_onlyoffice:
        raise InstallerError("OnlyOffice configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(onlyoffice.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(onlyoffice.get("max_ram", ""))):
        raise InstallerError("Invalid OnlyOffice size configuration")
    if ram_to_bytes(onlyoffice["max_ram"]) < 4294967296:
        raise InstallerError("OnlyOffice max_ram must be at least 4Gi")
    if not isinstance(onlyoffice.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(onlyoffice["hostname"]):
        raise InstallerError("Invalid onlyoffice.hostname")
    if type(onlyoffice.get("node_port")) is not int or not 30000 <= onlyoffice["node_port"] <= 32767:
        raise InstallerError("Invalid onlyoffice.node_port")
    opencloud = cloud["opencloud"]
    expected_opencloud = {"storage_size", "max_ram", "hostname", "node_port"}
    if not isinstance(opencloud, dict) or set(opencloud) != expected_opencloud:
        raise InstallerError("OpenCloud configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(opencloud.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(opencloud.get("max_ram", ""))):
        raise InstallerError("Invalid OpenCloud size configuration")
    if not isinstance(opencloud.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(opencloud["hostname"]):
        raise InstallerError("Invalid opencloud.hostname")
    if type(opencloud.get("node_port")) is not int or not 30000 <= opencloud["node_port"] <= 32767:
        raise InstallerError("Invalid opencloud.node_port")
    if opencloud["hostname"] == onlyoffice["hostname"] or opencloud["node_port"] == onlyoffice["node_port"]:
        raise InstallerError("OpenCloud and OnlyOffice endpoints must differ")
    grist = cloud["grist"]
    expected_grist = {"storage_size", "max_ram", "database_name", "database_username", "default_email", "hostname", "node_port"}
    if not isinstance(grist, dict) or set(grist) != expected_grist:
        raise InstallerError("Grist configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(grist.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(grist.get("max_ram", ""))):
        raise InstallerError("Invalid Grist size configuration")
    if ram_to_bytes(grist["max_ram"]) < 536870912:
        raise InstallerError("Grist max_ram must be at least 512Mi")
    if not IDENTIFIER_PATTERN.fullmatch(str(grist.get("database_name", ""))) or not IDENTIFIER_PATTERN.fullmatch(str(grist.get("database_username", ""))):
        raise InstallerError("Grist database identifiers are invalid")
    if grist["database_name"].lower() in {"postgres", "template0", "template1"} or grist["database_username"].lower() in {"postgres", "replication"} or grist["database_username"].lower().startswith("pg_"):
        raise InstallerError("Grist cannot use a PostgreSQL system database or role")
    if not isinstance(grist.get("default_email"), str) or not EMAIL_PATTERN.fullmatch(grist["default_email"]):
        raise InstallerError("Invalid grist.default_email")
    if not isinstance(grist.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(grist["hostname"]):
        raise InstallerError("Invalid grist.hostname")
    if type(grist.get("node_port")) is not int or not 30000 <= grist["node_port"] <= 32767:
        raise InstallerError("Invalid grist.node_port")
    affine = cloud["affine"]
    expected_affine = {"storage_size", "max_ram", "redis_max_ram", "database_name", "database_username", "hostname", "node_port"}
    if not isinstance(affine, dict) or set(affine) != expected_affine:
        raise InstallerError("AFFiNE configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(affine.get("storage_size", ""))):
        raise InstallerError("Invalid AFFiNE storage configuration")
    for key in ("max_ram", "redis_max_ram"):
        if not RAM_PATTERN.fullmatch(str(affine.get(key, ""))):
            raise InstallerError(f"Invalid affine.{key}")
    if ram_to_bytes(affine["max_ram"]) < 2147483648 or ram_to_bytes(affine["redis_max_ram"]) < 134217728:
        raise InstallerError("AFFiNE memory limits are too small")
    if not IDENTIFIER_PATTERN.fullmatch(str(affine.get("database_name", ""))) or not IDENTIFIER_PATTERN.fullmatch(str(affine.get("database_username", ""))):
        raise InstallerError("AFFiNE database identifiers are invalid")
    if affine["database_name"].lower() in {"postgres", "template0", "template1"} or affine["database_username"].lower() in {"postgres", "replication"} or affine["database_username"].lower().startswith("pg_"):
        raise InstallerError("AFFiNE cannot use a PostgreSQL system database or role")
    if not isinstance(affine.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(affine["hostname"]):
        raise InstallerError("Invalid affine.hostname")
    if type(affine.get("node_port")) is not int or not 30000 <= affine["node_port"] <= 32767:
        raise InstallerError("Invalid affine.node_port")
    public_hostnames = [onlyoffice["hostname"], opencloud["hostname"], grist["hostname"], affine["hostname"]]
    if len(public_hostnames) != len(set(public_hostnames)):
        raise InstallerError("Every public application hostname must be unique")
    expected_stalwart = {
        "storage_size", "max_ram", "database_name", "database_username", "domain", "forwarding_domain", "hostname",
        "acme_contact", "admin_username", "mailbox_username", "relay_host", "relay_port", "relay_implicit_tls", "relay_username",
        "https_node_port", "smtp_node_port", "submissions_node_port", "submission_node_port", "imaps_node_port",
    }
    if not isinstance(stalwart, dict) or set(stalwart) != expected_stalwart:
        raise InstallerError("Stalwart configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(stalwart.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(stalwart.get("max_ram", ""))):
        raise InstallerError("Invalid Stalwart size configuration")
    if not IDENTIFIER_PATTERN.fullmatch(str(stalwart.get("database_name", ""))) or not IDENTIFIER_PATTERN.fullmatch(str(stalwart.get("database_username", ""))):
        raise InstallerError("Stalwart database identifiers are invalid")
    if stalwart["database_name"].lower() in {"postgres", "template0", "template1"} or stalwart["database_username"].lower() in {"postgres", "replication"} or stalwart["database_username"].lower().startswith("pg_"):
        raise InstallerError("Stalwart cannot use a PostgreSQL system database or role")
    for key in ("domain", "forwarding_domain", "hostname", "relay_host"):
        if not isinstance(stalwart.get(key), str) or not DOMAIN_PATTERN.fullmatch(stalwart[key]):
            raise InstallerError(f"Invalid stalwart.{key}")
    if stalwart["forwarding_domain"] == stalwart["domain"] or not stalwart["forwarding_domain"].endswith("." + stalwart["domain"]):
        raise InstallerError("Stalwart forwarding_domain must be a subdomain of domain")
    if stalwart["hostname"] == stalwart["domain"] or not stalwart["hostname"].endswith("." + stalwart["domain"]):
        raise InstallerError("Stalwart hostname must be a subdomain of domain")
    if stalwart["hostname"] == stalwart["forwarding_domain"]:
        raise InstallerError("Stalwart hostname and forwarding_domain must differ")
    for key in ("acme_contact", "relay_username"):
        if not isinstance(stalwart.get(key), str) or not EMAIL_PATTERN.fullmatch(stalwart[key]):
            raise InstallerError(f"Invalid stalwart.{key}")
    for key in ("admin_username", "mailbox_username"):
        if not isinstance(stalwart.get(key), str) or not MAILBOX_PATTERN.fullmatch(stalwart[key]):
            raise InstallerError(f"Invalid stalwart.{key}")
    if stalwart["admin_username"] == stalwart["mailbox_username"]:
        raise InstallerError("Stalwart administrator and mailbox usernames must differ")
    if type(stalwart.get("relay_implicit_tls")) is not bool or type(stalwart.get("relay_port")) is not int or not 1 <= stalwart["relay_port"] <= 65535:
        raise InstallerError("Invalid Stalwart relay configuration")
    stalwart_node_ports = [stalwart[key] for key in ("https_node_port", "smtp_node_port", "submissions_node_port", "submission_node_port", "imaps_node_port")]
    if any(type(port) is not int or not 30000 <= port <= 32767 for port in stalwart_node_ports) or len(set(stalwart_node_ports)) != len(stalwart_node_ports):
        raise InstallerError("Stalwart NodePorts must be valid and unique")
    zabbix = cloud["zabbix"]
    expected_zabbix = {"storage_size", "database_name", "database_username", "server_node_port", "web_node_port", "hostname", "admin_username", "agent_server_active"}
    if not isinstance(zabbix, dict) or set(zabbix) != expected_zabbix:
        raise InstallerError("Missing zabbix configuration")
    for key in ("database_name", "database_username", "hostname", "admin_username", "agent_server_active"):
        if not isinstance(zabbix.get(key), str) or not zabbix[key]:
            raise InstallerError(f"Missing zabbix.{key}")
    if any(character in zabbix["hostname"] or character in zabbix["admin_username"] for character in ("\r", "\n")):
        raise InstallerError("Zabbix hostname and administrator name must be single-line values")
    if not IDENTIFIER_PATTERN.fullmatch(zabbix["database_name"]) or not IDENTIFIER_PATTERN.fullmatch(zabbix["database_username"]):
        raise InstallerError("Zabbix database identifiers are invalid")
    if zabbix["database_name"].lower() in {"postgres", "template0", "template1"} or zabbix["database_username"].lower() in {"postgres", "replication"} or zabbix["database_username"].lower().startswith("pg_"):
        raise InstallerError("Zabbix cannot use a PostgreSQL system database or role")
    if not QUOTA_PATTERN.fullmatch(str(zabbix.get("storage_size", ""))):
        raise InstallerError("Invalid zabbix.storage_size")
    active_server = re.fullmatch(r"[^\s,]+(?::([0-9]{1,5}))?", zabbix["agent_server_active"])
    if len(zabbix["hostname"]) > 128 or active_server is None or (active_server.group(1) is not None and not 1 <= int(active_server.group(1)) <= 65535):
        raise InstallerError("Invalid Zabbix hostname or active server")
    for key in ("server_node_port", "web_node_port"):
        if type(zabbix.get(key)) is not int or not 30000 <= zabbix[key] <= 32767:
            raise InstallerError(f"Invalid zabbix.{key}")
    if zabbix["server_node_port"] == zabbix["web_node_port"]:
        raise InstallerError("Zabbix NodePorts must differ")
    external_node_ports = stalwart_node_ports + [zabbix["server_node_port"], zabbix["web_node_port"], onlyoffice["node_port"], opencloud["node_port"], grist["node_port"], affine["node_port"]]
    if len(external_node_ports) != len(set(external_node_ports)):
        raise InstallerError("Every public NodePort must be unique")


def validate_secrets_configuration(configuration: Mapping[str, Any]) -> None:
    schemas = {
        "storage": {"encryption_passphrase"},
        "postgres": {"admin_password"},
        "meilisearch": {"master_key"},
        "stalwart": {"database_password", "admin_password", "mailbox_password", "relay_password"},
        "zabbix": {"database_password", "admin_password"},
        "onlyoffice": {"jwt_secret"},
        "opencloud": {"admin_password"},
        "grist": {"database_password", "session_secret", "boot_key"},
        "affine": {"database_password"},
    }
    secrets_root = configuration.get("private_cloud_secrets")
    if not isinstance(secrets_root, dict) or set(secrets_root) != set(schemas):
        raise InstallerError("Encrypted configuration is incomplete")
    for section, keys in schemas.items():
        if not isinstance(secrets_root.get(section), dict) or set(secrets_root[section]) != keys:
            raise InstallerError("Encrypted configuration has missing or unknown keys")
        for key in keys:
            if not isinstance(secrets_root[section].get(key), str) or not secrets_root[section][key]:
                raise InstallerError(f"Encrypted configuration is missing {section}.{key}")
    if len(secrets_root["meilisearch"]["master_key"].encode()) < 16:
        raise InstallerError("The Meilisearch master key must contain at least 16 bytes")
    if len(secrets_root["onlyoffice"]["jwt_secret"]) < 32:
        raise InstallerError("The OnlyOffice JWT secret must contain at least 32 characters")
    if len(secrets_root["grist"]["session_secret"]) < 32:
        raise InstallerError("The Grist session secret must contain at least 32 characters")
    if len(secrets_root["grist"]["boot_key"]) < 16:
        raise InstallerError("The Grist boot key must contain at least 16 characters")
    if len(secrets_root["affine"]["database_password"]) < 16:
        raise InstallerError("The AFFiNE database password must contain at least 16 characters")
    passphrase_length = len(secrets_root["storage"]["encryption_passphrase"].encode())
    if not 8 <= passphrase_length <= 512:
        raise InstallerError("The storage passphrase must contain 8 to 512 bytes")


def require_commands(commands: Sequence[str]) -> None:
    missing = [command for command in commands if shutil.which(command) is None]
    if missing:
        raise InstallerError(f"Required command not found: {missing[0]}")


def require_kubernetes_readiness() -> None:
    require_commands(["ansible-galaxy"])
    result = run_command(["ansible-galaxy", "collection", "list", "kubernetes.core"])
    if "kubernetes.core" not in result.stdout:
        raise InstallerError("The kubernetes.core Ansible collection is not installed")
    run_command(["python3", "-c", "import kubernetes"])


def run_command(args: Sequence[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(args), input=input_text, text=True, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", "") or ""
        raise InstallerError(f"Command failed: {args[0]}{(': ' + detail.strip()) if detail.strip() else ''}") from error


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def pool_exists() -> bool:
    if not command_exists("zpool"):
        return False
    result = subprocess.run(["zpool", "list", "-H", "-o", "name", POOL_NAME], check=False, capture_output=True, text=True)
    return result.returncode == 0 and POOL_NAME in result.stdout.split()


def encrypt_secrets(plaintext: Path, encrypted: Path, password_file: Path) -> None:
    temporary = encrypted.with_name(f".{encrypted.name}.{secrets.token_hex(8)}")
    try:
        run_command(["ansible-vault", "encrypt", str(plaintext), "--vault-password-file", str(password_file), "--output", str(temporary)])
        validate_vault_ciphertext(temporary)
        os.chmod(temporary, 0o600)
        temporary.replace(encrypted)
    finally:
        temporary.unlink(missing_ok=True)
        plaintext.unlink(missing_ok=True)


def decrypt_secrets(encrypted: Path, plaintext: Path, password_file: Path) -> None:
    validate_vault_ciphertext(encrypted)
    run_command(["ansible-vault", "decrypt", str(encrypted), "--vault-password-file", str(password_file), "--output", str(plaintext)])
    os.chmod(plaintext, 0o600)


def rekey_secrets(encrypted: Path, old_password: Path, new_password: Path) -> None:
    temporary = encrypted.with_name(f".{encrypted.name}.rekey.{secrets.token_hex(8)}")
    try:
        shutil.copy2(encrypted, temporary)
        os.chmod(temporary, 0o600)
        run_command(["ansible-vault", "rekey", str(temporary), "--vault-password-file", str(old_password), "--new-vault-password-file", str(new_password)])
        validate_vault_ciphertext(temporary)
        temporary.replace(encrypted)
        os.chmod(encrypted, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def validate_vault_ciphertext(path: Path) -> None:
    try:
        with path.open("rb") as encrypted:
            header = encrypted.readline()
    except OSError as error:
        raise InstallerError(f"Cannot read Vault output: {path}") from error
    if not re.fullmatch(rb"\$ANSIBLE_VAULT;[0-9]+\.[0-9]+;AES[0-9]+\n", header):
        raise InstallerError("ansible-vault did not produce a valid ciphertext header")


def write_secret_file(configuration: Mapping[str, Any], path: Path = TEMP_SECRET_FILE) -> None:
    validate_secrets_configuration(configuration)
    atomic_write(path, dump_yaml(configuration), 0o600)


def write_password_file(password: str, path: Path = VAULT_PASSWORD_FILE) -> None:
    atomic_write(path, password + "\n", 0o600)


def redact_secrets(configuration: Mapping[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(configuration))
    root = result.get("private_cloud_secrets", {})
    for section in root.values() if isinstance(root, dict) else ():
        if isinstance(section, dict):
            for key in section:
                section[key] = "configured"
    return result


def ram_to_bytes(value: str) -> int:
    units = {"Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4}
    return int(value[:-2]) * units[value[-2:]]


class InstallerError(RuntimeError):
    """An expected installer failure."""
