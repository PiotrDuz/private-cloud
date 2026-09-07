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
ANSIBLE_CONFIG = Path(__file__).resolve().parent / "ansible.cfg"
LOCK_FILE = RUNTIME_DIRECTORY / "installer.lock"
VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "vault-password"
OLD_VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "old-vault-password"
TEMP_SECRET_FILE = RUNTIME_DIRECTORY / "secrets.yml"
TEMP_PUBLIC_FILE = RUNTIME_DIRECTORY / "public.yml"
TEMP_RUNTIME_FILE = RUNTIME_DIRECTORY / "runtime.yml"
KUBECONFIG_FILE = RUNTIME_DIRECTORY / "kubeconfig"
INSTALLER_LOG = RUNTIME_DIRECTORY / "installer.log"
SERVICE_CATALOG = Path(__file__).resolve().parent / "service_catalog.yml"
MODES = ("create", "update", "reapply", "rotate")
CURRENT_SCHEMA_VERSION = 4
CURRENT_SECRETS_SCHEMA_VERSION = 2
SECRET_SCHEMAS = {
    "storage": {"encryption_passphrase"},
    "postgres": {"admin_password"},
    "meilisearch": {"master_key"},
    "stalwart": {"database_password", "admin_password", "mailbox_password", "relay_password"},
    "zabbix": {"database_password", "admin_password"},
    "onlyoffice": {"jwt_secret"},
    "opencloud": {"admin_password"},
    "grist": {"database_password", "session_secret", "boot_key"},
    "affine": {"database_password"},
    "immich": {"database_password"},
}
SECRET_STAGES = {
    "storage": "zfs",
    "postgres": "postgres",
    "meilisearch": "meilisearch",
    "stalwart": "stalwart",
    "zabbix": "zabbix_server",
    "onlyoffice": "onlyoffice",
    "opencloud": "opencloud",
    "grist": "grist",
    "affine": "affine",
    "immich": "immich",
}
QUOTA_PATTERN = re.compile(r"[1-9][0-9]*[KMGTPE]")
RAM_PATTERN = re.compile(r"[1-9][0-9]*(?:Ki|Mi|Gi|Ti)")
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
    if set(configuration) != {"schema_version", "private_cloud"} or not isinstance(configuration["private_cloud"], dict):
        raise InstallerError("Public configuration must contain only schema_version and private_cloud")
    if configuration["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise InstallerError(f"Public configuration schema_version must be {CURRENT_SCHEMA_VERSION}")
    cloud = configuration["private_cloud"]
    expected = {"stages", "storage", "k0s", "postgres", "meilisearch", "tika", "bleve", "onlyoffice", "opencloud", "grist", "manticore", "redis_affine", "affine", "immich", "stalwart", "zabbix"}
    if set(cloud) != expected:
        raise InstallerError("Public configuration has missing or unknown sections")
    stages = cloud["stages"]
    if not isinstance(stages, dict) or set(stages) != {"zfs", "k0s", "intel_gpu", "postgres", "meilisearch", "stalwart", "tika", "bleve", "onlyoffice", "opencloud", "grist", "manticore", "redis_affine", "affine", "immich", "zabbix_server", "zabbix_agent"}:
        raise InstallerError("Stage configuration is incomplete")
    if any(type(value) is not bool for value in stages.values()):
        raise InstallerError("Every stage flag must be Boolean")
    dependencies = load_yaml(SERVICE_CATALOG).get("private_cloud_stage_dependencies")
    if not isinstance(dependencies, dict) or set(dependencies) != set(stages) - {"zfs"}:
        raise InstallerError("Service catalog stage dependencies are incomplete")
    if any(not isinstance(required, list) or any(dependency not in stages for dependency in required) for required in dependencies.values()):
        raise InstallerError("Service catalog stage dependencies are invalid")
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
    if not isinstance(k0s, dict) or set(k0s) != {"config_quota", "images_quota", "ephemeral_quota"}:
        raise InstallerError("k0s configuration has missing or unknown keys")
    for key in ("config_quota", "images_quota", "ephemeral_quota"):
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
    expected_onlyoffice = {"storage_size", "max_ram", "hostname"}
    if not isinstance(onlyoffice, dict) or set(onlyoffice) != expected_onlyoffice:
        raise InstallerError("OnlyOffice configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(onlyoffice.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(onlyoffice.get("max_ram", ""))):
        raise InstallerError("Invalid OnlyOffice size configuration")
    if ram_to_bytes(onlyoffice["max_ram"]) < 4294967296:
        raise InstallerError("OnlyOffice max_ram must be at least 4Gi")
    if not isinstance(onlyoffice.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(onlyoffice["hostname"]):
        raise InstallerError("Invalid onlyoffice.hostname")
    opencloud = cloud["opencloud"]
    expected_opencloud = {"storage_size", "max_ram", "hostname"}
    if not isinstance(opencloud, dict) or set(opencloud) != expected_opencloud:
        raise InstallerError("OpenCloud configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(opencloud.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(opencloud.get("max_ram", ""))):
        raise InstallerError("Invalid OpenCloud size configuration")
    if not isinstance(opencloud.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(opencloud["hostname"]):
        raise InstallerError("Invalid opencloud.hostname")
    if opencloud["hostname"] == onlyoffice["hostname"]:
        raise InstallerError("OpenCloud and OnlyOffice endpoints must differ")
    grist = cloud["grist"]
    expected_grist = {"storage_size", "max_ram", "default_email", "hostname"}
    if not isinstance(grist, dict) or set(grist) != expected_grist:
        raise InstallerError("Grist configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(grist.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(grist.get("max_ram", ""))):
        raise InstallerError("Invalid Grist size configuration")
    if ram_to_bytes(grist["max_ram"]) < 536870912:
        raise InstallerError("Grist max_ram must be at least 512Mi")
    if not isinstance(grist.get("default_email"), str) or not EMAIL_PATTERN.fullmatch(grist["default_email"]):
        raise InstallerError("Invalid grist.default_email")
    if not isinstance(grist.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(grist["hostname"]):
        raise InstallerError("Invalid grist.hostname")
    manticore = cloud["manticore"]
    if not isinstance(manticore, dict) or set(manticore) != {"storage_size", "max_ram"}:
        raise InstallerError("Manticore configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(manticore.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(manticore.get("max_ram", ""))):
        raise InstallerError("Invalid Manticore size configuration")
    redis_affine = cloud["redis_affine"]
    if not isinstance(redis_affine, dict) or set(redis_affine) != {"max_ram"}:
        raise InstallerError("Redis for AFFiNE configuration has missing or unknown keys")
    if not RAM_PATTERN.fullmatch(str(redis_affine.get("max_ram", ""))) or ram_to_bytes(redis_affine["max_ram"]) < 134217728:
        raise InstallerError("Invalid redis_affine.max_ram")
    affine = cloud["affine"]
    expected_affine = {"storage_size", "max_ram", "hostname"}
    if not isinstance(affine, dict) or set(affine) != expected_affine:
        raise InstallerError("AFFiNE configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(affine.get("storage_size", ""))):
        raise InstallerError("Invalid AFFiNE storage configuration")
    for key in ("max_ram",):
        if not RAM_PATTERN.fullmatch(str(affine.get(key, ""))):
            raise InstallerError(f"Invalid affine.{key}")
    if ram_to_bytes(affine["max_ram"]) < 2147483648:
        raise InstallerError("AFFiNE memory limit is too small")
    if not isinstance(affine.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(affine["hostname"]):
        raise InstallerError("Invalid affine.hostname")
    immich = cloud["immich"]
    expected_immich = {"storage_size", "hostname", "timezone", "max_ram", "max_cpu", "machine_learning_max_ram", "machine_learning_max_cpu", "machine_learning_accelerator", "valkey_max_ram", "valkey_max_cpu"}
    if not isinstance(immich, dict) or set(immich) != expected_immich:
        raise InstallerError("Immich configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(immich.get("storage_size", ""))):
        raise InstallerError("Invalid immich.storage_size")
    for key in ("max_ram", "machine_learning_max_ram", "valkey_max_ram"):
        if not RAM_PATTERN.fullmatch(str(immich.get(key, ""))):
            raise InstallerError(f"Invalid immich.{key}")
    if ram_to_bytes(immich["max_ram"]) < 2147483648 or ram_to_bytes(immich["machine_learning_max_ram"]) < 1073741824 or ram_to_bytes(immich["valkey_max_ram"]) < 134217728:
        raise InstallerError("Immich memory limits are too small")
    for key in ("max_cpu", "machine_learning_max_cpu", "valkey_max_cpu"):
        if not isinstance(immich.get(key), str) or not re.fullmatch(r"(?:[1-9][0-9]*m|[1-9][0-9]*)", immich[key]):
            raise InstallerError(f"Invalid immich.{key}")
    if cpu_to_millicores(immich["max_cpu"]) < 500 or cpu_to_millicores(immich["machine_learning_max_cpu"]) < 250 or cpu_to_millicores(immich["valkey_max_cpu"]) < 100:
        raise InstallerError("Immich CPU limits are below their requests")
    if immich.get("machine_learning_accelerator") not in {"cpu", "openvino"}:
        raise InstallerError("Invalid immich.machine_learning_accelerator")
    if immich["machine_learning_accelerator"] == "openvino" and not stages["intel_gpu"]:
        raise InstallerError("Immich OpenVINO acceleration requires the Intel GPU stage")
    if not isinstance(immich.get("timezone"), str) or not re.fullmatch(r"[A-Za-z_+-]+/[A-Za-z_+/-]+", immich["timezone"]):
        raise InstallerError("Invalid immich.timezone")
    if not isinstance(immich.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(immich["hostname"]):
        raise InstallerError("Invalid immich.hostname")
    public_hostnames = [onlyoffice["hostname"], opencloud["hostname"], grist["hostname"], affine["hostname"], immich["hostname"]]
    if len(public_hostnames) != len(set(public_hostnames)):
        raise InstallerError("Every public application hostname must be unique")
    expected_stalwart = {
        "storage_size", "max_ram", "domain", "forwarding_domain", "hostname",
        "acme_contact", "admin_username", "mailbox_username", "relay_host", "relay_port", "relay_implicit_tls", "relay_username",
    }
    if not isinstance(stalwart, dict) or set(stalwart) != expected_stalwart:
        raise InstallerError("Stalwart configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(stalwart.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(stalwart.get("max_ram", ""))):
        raise InstallerError("Invalid Stalwart size configuration")
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
    zabbix = cloud["zabbix"]
    expected_zabbix = {"storage_size", "admin_username"}
    if not isinstance(zabbix, dict) or set(zabbix) != expected_zabbix:
        raise InstallerError("Missing zabbix configuration")
    for key in ("admin_username",):
        if not isinstance(zabbix.get(key), str) or not zabbix[key]:
            raise InstallerError(f"Missing zabbix.{key}")
    if any(character in zabbix["admin_username"] for character in ("\r", "\n")):
        raise InstallerError("Zabbix administrator name must be a single-line value")
    if not QUOTA_PATTERN.fullmatch(str(zabbix.get("storage_size", ""))):
        raise InstallerError("Invalid zabbix.storage_size")


def validate_secrets_configuration(configuration: Mapping[str, Any], stages: Mapping[str, bool]) -> None:
    if set(configuration) != {"secrets_schema_version", "private_cloud_secrets"}:
        raise InstallerError("Encrypted configuration has missing or unknown top-level keys")
    if configuration["secrets_schema_version"] != CURRENT_SECRETS_SCHEMA_VERSION:
        raise InstallerError(f"Encrypted configuration secrets_schema_version must be {CURRENT_SECRETS_SCHEMA_VERSION}")
    secrets_root = configuration.get("private_cloud_secrets")
    if not isinstance(secrets_root, dict) or not set(secrets_root) <= set(SECRET_SCHEMAS):
        raise InstallerError("Encrypted configuration has unknown sections")
    for section, values in secrets_root.items():
        if not isinstance(values, dict) or not set(values) <= SECRET_SCHEMAS[section]:
            raise InstallerError("Encrypted configuration has missing or unknown keys")
        for key, value in values.items():
            if not isinstance(value, str) or not value:
                raise InstallerError(f"Encrypted configuration is missing {section}.{key}")
    for section, schema in SECRET_SCHEMAS.items():
        if stages.get(SECRET_STAGES[section]) and (section not in secrets_root or set(secrets_root[section]) != schema):
            raise InstallerError(f"Encrypted configuration is missing credentials for enabled stage {SECRET_STAGES[section]}")
    if "meilisearch" in secrets_root and "master_key" in secrets_root["meilisearch"] and len(secrets_root["meilisearch"]["master_key"].encode()) < 16:
        raise InstallerError("The Meilisearch master key must contain at least 16 bytes")
    if "onlyoffice" in secrets_root and "jwt_secret" in secrets_root["onlyoffice"] and len(secrets_root["onlyoffice"]["jwt_secret"]) < 32:
        raise InstallerError("The OnlyOffice JWT secret must contain at least 32 characters")
    if "grist" in secrets_root and "session_secret" in secrets_root["grist"] and len(secrets_root["grist"]["session_secret"]) < 32:
        raise InstallerError("The Grist session secret must contain at least 32 characters")
    if "grist" in secrets_root and "boot_key" in secrets_root["grist"] and len(secrets_root["grist"]["boot_key"]) < 16:
        raise InstallerError("The Grist boot key must contain at least 16 characters")
    if "affine" in secrets_root and "database_password" in secrets_root["affine"] and len(secrets_root["affine"]["database_password"]) < 16:
        raise InstallerError("The AFFiNE database password must contain at least 16 characters")
    if "immich" in secrets_root and "database_password" in secrets_root["immich"] and len(secrets_root["immich"]["database_password"]) < 16:
        raise InstallerError("The Immich database password must contain at least 16 characters")
    passphrase = secrets_root.get("storage", {}).get("encryption_passphrase")
    if passphrase is not None and not 8 <= len(passphrase.encode()) <= 512:
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


def run_command(
    args: Sequence[str],
    *,
    input_text: str | None = None,
    environment: Mapping[str, str] | None = None,
    stage: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command_environment = os.environ.copy()
    if environment:
        command_environment.update(environment)
    try:
        return subprocess.run(list(args), input=input_text, text=True, check=True, capture_output=True, env=command_environment)
    except (OSError, subprocess.CalledProcessError) as error:
        stdout = getattr(error, "stdout", "") or ""
        stderr = getattr(error, "stderr", "") or ""
        log_path = _write_command_failure_log(args, stdout, stderr)
        failed_stage, failed_task, detail = _summarize_command_failure(args[0], stdout, stderr, stage)
        raise InstallerError(
            f"Command failed; stage={failed_stage}; task={failed_task}; error={detail}; detailed_log={log_path}"
        ) from error


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


def write_secret_file(configuration: Mapping[str, Any], stages: Mapping[str, bool], path: Path = TEMP_SECRET_FILE) -> None:
    validate_secrets_configuration(configuration, stages)
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



def cpu_to_millicores(value: str) -> int:
    return int(value[:-1]) if value.endswith("m") else int(value) * 1000


def _write_command_failure_log(args: Sequence[str], stdout: str, stderr: str) -> Path:
    ensure_runtime_directory()
    if INSTALLER_LOG.is_symlink():
        raise InstallerError(f"Unsafe symbolic-link installer log: {INSTALLER_LOG}")
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(INSTALLER_LOG, flags, 0o600)
    details = os.fstat(descriptor)
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0:
        os.close(descriptor)
        raise InstallerError("Installer log must be a root-owned regular file")
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(f"command: {args[0]}\nstdout:\n{stdout}\nstderr:\n{stderr}\n")
    return INSTALLER_LOG


def _summarize_command_failure(command: str, stdout: str, stderr: str, stage: str | None) -> tuple[str, str, str]:
    task_matches = re.findall(r"(?m)^TASK \[([^]]+)]", stdout)
    task = task_matches[-1] if task_matches else command
    inferred_stage = task.split(" : ", 1)[0] if " : " in task else stage or command
    failure_lines = re.findall(r"(?m)^fatal: .*?FAILED! => (.+)$", stdout)
    detail = "Ansible task failed" if failure_lines else "Command execution failed"
    return (
        _sanitize_failure_text(inferred_stage, 80),
        _sanitize_failure_text(task, 160),
        _sanitize_failure_text(detail, 400),
    )


def _sanitize_failure_text(value: str, limit: int) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    text = re.sub(r"(?i)(password|passphrase|secret|token|key)(\s*[=:]\s*)([^\s,;}]+)", r"\1\2[redacted]", text)
    text = " ".join(text.split())
    return (text[: limit - 3] + "...") if len(text) > limit else text


class InstallerError(RuntimeError):
    """An expected installer failure."""
