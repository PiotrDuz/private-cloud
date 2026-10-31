"""Safe input, configuration, and command helpers for the Ansible installer."""

from __future__ import annotations

import copy
import getpass
import ipaddress
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
CONFIGURATION_DATASET = "tank/secure/backup/private-cloud-config"
CONFIGURATION_DIRECTORY = Path("/tank/secure/backup/private-cloud-config")
PUBLIC_CONFIGURATION = CONFIGURATION_DIRECTORY / "private-cloud.yml"
SECRETS_CONFIGURATION = CONFIGURATION_DIRECTORY / "private-cloud.secrets.yml"
EXAMPLE_CONFIGURATION = Path(__file__).resolve().parent / "config" / "private-cloud.example.yml"
INVENTORY = Path(__file__).resolve().parent / "inventory" / "hosts.yml"
PLAYBOOK = Path(__file__).resolve().parent / "site.yml"
VALIDATION_PLAYBOOK = Path(__file__).resolve().parent / "validate.yml"
ANSIBLE_CONFIG = Path(__file__).resolve().parent / "ansible.cfg"
LOCK_FILE = RUNTIME_DIRECTORY / "installer.lock"
VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "vault-password"
OLD_VAULT_PASSWORD_FILE = RUNTIME_DIRECTORY / "old-vault-password"
TEMP_SECRET_FILE = RUNTIME_DIRECTORY / "secrets.yml"
TEMP_PUBLIC_FILE = RUNTIME_DIRECTORY / "public.yml"
TEMP_RESOLVED_FILE = RUNTIME_DIRECTORY / "resolved.yml"
TEMP_ENCRYPTED_FILE = RUNTIME_DIRECTORY / "private-cloud.secrets.yml"
TEMP_RUNTIME_FILE = RUNTIME_DIRECTORY / "runtime.yml"
KUBECONFIG_FILE = RUNTIME_DIRECTORY / "kubeconfig"
LUKS_PASSPHRASE_FILE = RUNTIME_DIRECTORY / "luks-passphrase"
LUKS_KEY_FILE = RUNTIME_DIRECTORY / "luks-key"
INSTALLER_LOG = RUNTIME_DIRECTORY / "installer.log"
SERVICE_CATALOG = Path(__file__).resolve().parent / "service_catalog.yml"
MODES = ("create", "update", "reapply", "rotate", "validate")
CURRENT_SCHEMA_VERSION = 17
CURRENT_SECRETS_SCHEMA_VERSION = 9
SECRET_SCHEMAS = {
    "storage": {"encryption_passphrase"},
    "postgres": {"admin_password"},
    "meilisearch": {"master_key"},
    "stalwart": {"database_password", "admin_password", "mailbox_password", "relay_password", "certificate_dns_api_token"},
    "zabbix": {"database_password", "admin_password", "agent_psk"},
    "onlyoffice": {"jwt_secret"},
    "opencloud": {"admin_password", "wopi_secret"},
    "grist": {"database_password", "session_secret", "boot_key", "oidc_client_secret", "oidc_cookie_secret"},
    "affine": {"database_password", "oidc_client_secret", "admin_password"},
    "immich": {"database_password", "oidc_client_secret", "admin_password"},
    "networking": {"cloudflare_api_token", "cloudflare_ddns_api_token", "amneziawg_admin_password"},
    "logging": {"admin_password"},
    "media": {"wireguard_private_key", "wireguard_preshared_key", "proxy_password", "qbittorrent_password", "jellyfin_admin_password"},
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
    "networking": "networking",
    "media": "media",
    "logging": "logging",
}
ADMIN_PASSWORDS = {
    ("postgres", "admin_password"),
    ("stalwart", "admin_password"),
    ("stalwart", "mailbox_password"),
    ("opencloud", "admin_password"),
    ("zabbix", "admin_password"),
    ("logging", "admin_password"),
    ("media", "qbittorrent_password"),
    ("media", "jellyfin_admin_password"),
    ("immich", "admin_password"),
    ("affine", "admin_password"),
    ("networking", "amneziawg_admin_password"),
}
MACHINE_SECRETS = {
    ("meilisearch", "master_key"),
    ("onlyoffice", "jwt_secret"),
    ("opencloud", "wopi_secret"),
    ("grist", "database_password"),
    ("grist", "session_secret"),
    ("grist", "boot_key"),
    ("grist", "oidc_client_secret"),
    ("grist", "oidc_cookie_secret"),
    ("affine", "database_password"),
    ("affine", "oidc_client_secret"),
    ("immich", "database_password"),
    ("immich", "oidc_client_secret"),
    ("stalwart", "database_password"),
    ("zabbix", "database_password"),
    ("zabbix", "agent_psk"),
    ("media", "proxy_password"),
}
WIREGUARD_KEY_PATTERN = re.compile(r"[A-Za-z0-9+/]{43}=")
COUNTRY_PATTERN = re.compile(r"[A-Z][A-Za-z .'-]{1,62}")
AIRVPN_WIREGUARD_PORTS = {1637, 47107}
ADMIN_PASSWORD_MINIMUM_LENGTH = 16
AFFINE_PASSWORD_MAXIMUM_LENGTH = 32
VENDOR_DEFAULT_PASSWORDS = {
    "admin", "administrator", "adminadmin", "adminpassword", "password", "passwordpassword", "changeme",
    "secret", "letmein", "welcome", "default", "root", "zabbix", "opencloud", "owncloud", "stalwart",
    "postgres", "postgresql", "qbittorrent", "openobserve",
}
CREATE_INTENT_FILE = Path("/var/lib/private-cloud/installer-create-intent.json")
STORAGE_CHECKS = Path(__file__).resolve().parent / "storage_checks.py"
IMMUTABLE_NETWORK_KEYS = ("pod_cidr", "service_cidr", "cluster_dns_ip")
QUOTA_PATTERN = re.compile(r"[1-9][0-9]*[KMGTPE]")
RAM_PATTERN = re.compile(r"[1-9][0-9]*(?:Ki|Mi|Gi|Ti)")
DOMAIN_PATTERN = re.compile(r"(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?=.{1,253}\Z)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,30}[A-Za-z0-9])?")
MAILBOX_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._+-]{0,62}[A-Za-z0-9])?")
TIMEZONE_PATTERN = re.compile(r"[A-Za-z_+-]+/[A-Za-z_+/-]+")
SERVICE_SUBDOMAINS = {
    "networking": "vpn",
    "media": "jellyfin",
    "stalwart": "mx-inbound",
    "onlyoffice": "onlyoffice",
    "opencloud": "cloud",
    "grist": "grist",
    "affine": "affine",
    "immich": "photos",
    "logging": "logs",
    "zabbix_server": "monitor",
}
AMNEZIAWG_UI_SUBDOMAIN = "vpn-admin"
RADARR_SUBDOMAIN = "radarr"
PROWLARR_SUBDOMAIN = "prowlarr"
BAZARR_SUBDOMAIN = "bazarr"
MEDIA_LAN_HOSTNAMES = ("radarr_hostname", "prowlarr_hostname", "bazarr_hostname")
HOMEPAGE_SUBDOMAIN = "www"
DERIVED_KEYS = {
    ("networking",): {"acme_email", "managed_records", "traefik_internal_ip", "traefik_cluster_ip", "lan_dns_cluster_ip", "zabbix_hostname", "homepage_hostname", "lan_only_records"},
    ("networking", "amneziawg"): {"hostname", "ui_hostname", "dns"},
    ("media",): {"hostname", "radarr_hostname", "prowlarr_hostname", "bazarr_hostname", "timezone"},
    ("onlyoffice",): {"hostname"},
    ("opencloud",): {"hostname", "admin_email"},
    ("grist",): {"hostname", "default_email"},
    ("affine",): {"hostname", "admin_email"},
    ("immich",): {"hostname", "timezone", "admin_email"},
    ("stalwart",): {"domain", "hostname", "acme_contact"},
    ("logging",): {"hostname"},
    ("boot_integrity",): {"interface", "host_address", "gateway_ip"},
}


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
    for name in (TEMP_SECRET_FILE.name, TEMP_PUBLIC_FILE.name, TEMP_RESOLVED_FILE.name, TEMP_ENCRYPTED_FILE.name, TEMP_RUNTIME_FILE.name, VAULT_PASSWORD_FILE.name, OLD_VAULT_PASSWORD_FILE.name, KUBECONFIG_FILE.name, LUKS_PASSPHRASE_FILE.name, LUKS_KEY_FILE.name):
        candidate = path / name
        if candidate.exists() or candidate.is_symlink():
            details = candidate.lstat()
            if candidate.is_symlink() or not stat.S_ISREG(details.st_mode):
                raise InstallerError(f"Unsafe non-regular runtime entry: {candidate}")
            if details.st_uid != 0:
                raise InstallerError(f"Runtime entry is not root-owned: {candidate}")
            candidate.unlink()


def require_configuration_dataset() -> None:
    require_commands(["zfs"])
    result = subprocess.run(
        ["zfs", "get", "-H", "-o", "property,value", "mounted,mountpoint", CONFIGURATION_DATASET],
        check=False, capture_output=True, text=True,
    )
    properties = dict(line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line)
    if result.returncode != 0 or properties.get("mounted") != "yes" or properties.get("mountpoint") != str(CONFIGURATION_DIRECTORY):
        raise InstallerError(f"Restore, unlock, and mount {CONFIGURATION_DATASET} at {CONFIGURATION_DIRECTORY} before running the installer")


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


def generate_secret(section: str, key: str) -> str | None:
    if (section, key) == ("zabbix", "agent_psk"):
        return secrets.token_hex(32)
    if (section, key) in ADMIN_PASSWORDS | MACHINE_SECRETS:
        return secrets.token_urlsafe(24)
    return None


def prompt_secret(prompt: str, *, confirm: bool = True, generated: str | None = None, reveal: bool = False) -> str:
    suffix = " (press Enter to generate)" if generated is not None else ""
    while True:
        value = getpass.getpass(f"{prompt}{suffix}: ")
        if not value and generated is not None:
            if reveal:
                print(f"Generated {prompt}: {generated}")
            return generated
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
    validate_resolved_configuration(resolve_public_configuration(configuration))


def resolve_public_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Expand the stored base values into the full contract that Ansible consumes."""
    if not isinstance(configuration.get("private_cloud"), dict):
        raise InstallerError("Public configuration must contain a private_cloud mapping")
    result = copy.deepcopy(dict(configuration))
    cloud = result["private_cloud"]
    if not {"domain", "admin_email", "timezone"} <= set(cloud) or any(not isinstance(_section(cloud, path), dict) for path in DERIVED_KEYS):
        raise InstallerError("Public configuration has missing or unknown sections")
    for path, keys in DERIVED_KEYS.items():
        stored = sorted(keys & set(_section(cloud, path)))
        if stored:
            raise InstallerError(f"Derived keys must not be stored: {'.'.join(path)}.{', '.join(stored)}")
    domain, admin_email, timezone = cloud.pop("domain"), cloud.pop("admin_email"), cloud.pop("timezone")
    if not isinstance(domain, str) or not DOMAIN_PATTERN.fullmatch(domain):
        raise InstallerError("Invalid private_cloud.domain")
    networking = cloud["networking"]
    lan = networking.pop("lan", None)
    if not isinstance(lan, dict) or set(lan) != {"interface", "address", "gateway"}:
        raise InstallerError("networking.lan must contain interface, address, and gateway")
    try:
        lan_address = ipaddress.IPv4Interface(lan["address"])
    except (TypeError, ValueError) as error:
        raise InstallerError("Invalid networking.lan.address") from error
    try:
        cluster_dns_address = ipaddress.IPv4Address(networking["cluster_dns_ip"])
    except (KeyError, TypeError, ValueError) as error:
        raise InstallerError("Invalid networking.cluster_dns_ip") from error
    stages = cloud["stages"] if isinstance(cloud.get("stages"), dict) else {}
    hostnames = {stage: f"{label}.{domain}" for stage, label in SERVICE_SUBDOMAINS.items()}
    homepage_hostname = f"{HOMEPAGE_SUBDOMAIN}.{domain}"
    networking.update({
        "acme_email": admin_email,
        "managed_records": [hostname for stage, hostname in hostnames.items() if stages.get(stage)] + ([homepage_hostname] if stages.get("networking") else []),
        "traefik_internal_ip": str(lan_address.ip),
        "traefik_cluster_ip": str(cluster_dns_address + 2),
        "lan_dns_cluster_ip": str(cluster_dns_address + 1),
        "zabbix_hostname": hostnames["zabbix_server"],
        "homepage_hostname": homepage_hostname,
    })
    networking["amneziawg"].update({"hostname": hostnames["networking"], "ui_hostname": f"{AMNEZIAWG_UI_SUBDOMAIN}.{domain}", "dns": [str(lan_address.ip)]})
    cloud["media"].update({"hostname": hostnames["media"], "radarr_hostname": f"{RADARR_SUBDOMAIN}.{domain}", "prowlarr_hostname": f"{PROWLARR_SUBDOMAIN}.{domain}", "bazarr_hostname": f"{BAZARR_SUBDOMAIN}.{domain}", "timezone": timezone})
    # LAN DNS answers these names; public DNS never publishes them.
    networking["lan_only_records"] = [networking["amneziawg"]["ui_hostname"]] + ([cloud["media"][key] for key in MEDIA_LAN_HOSTNAMES] if stages.get("media") else [])
    for stage in ("onlyoffice", "opencloud", "logging"):
        cloud[stage]["hostname"] = hostnames[stage]
    # Stalwart is the sign-in provider, so application administrators are the managed mailbox account.
    administrator = f"{cloud['stalwart'].get('mailbox_username')}@{domain}"
    cloud["opencloud"]["admin_email"] = administrator
    cloud["grist"].update({"hostname": hostnames["grist"], "default_email": administrator})
    cloud["affine"].update({"hostname": hostnames["affine"], "admin_email": administrator})
    cloud["immich"].update({"hostname": hostnames["immich"], "timezone": timezone, "admin_email": administrator})
    cloud["stalwart"].update({
        "domain": domain,
        "hostname": hostnames["stalwart"],
        "acme_contact": admin_email,
    })
    cloud["boot_integrity"].update({"interface": lan["interface"], "host_address": lan["address"], "gateway_ip": lan["gateway"]})
    return result


def discover_lan() -> dict[str, str] | None:
    routes = json.loads(run_command(["ip", "-j", "-4", "route", "show", "default"]).stdout or "[]")
    route = next((entry for entry in routes if entry.get("gateway") and entry.get("dev")), None)
    if route is None:
        return None
    interfaces = json.loads(run_command(["ip", "-j", "-4", "address", "show", "dev", route["dev"]]).stdout or "[]")
    addresses = [info for entry in interfaces for info in entry.get("addr_info", []) if info.get("scope") == "global"]
    if not addresses:
        return None
    return {"interface": route["dev"], "address": f"{addresses[0]['local']}/{addresses[0]['prefixlen']}", "gateway": route["gateway"]}


def discover_timezone() -> str:
    zone = os.path.realpath("/etc/localtime").partition("/zoneinfo/")[2]
    return zone if TIMEZONE_PATTERN.fullmatch(zone) else "Etc/UTC"


def validate_resolved_configuration(configuration: Mapping[str, Any]) -> None:
    if set(configuration) != {"schema_version", "private_cloud"} or not isinstance(configuration["private_cloud"], dict):
        raise InstallerError("Public configuration must contain only schema_version and private_cloud")
    if configuration["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise InstallerError(f"Public configuration schema_version must be {CURRENT_SCHEMA_VERSION}")
    cloud = configuration["private_cloud"]
    expected = {"stages", "storage", "k0s", "networking", "media", "postgres", "meilisearch", "tika", "bleve", "onlyoffice", "opencloud", "grist", "manticore", "redis_affine", "affine", "immich", "stalwart", "zabbix", "logging", "notifications", "boot_integrity"}
    if set(cloud) != expected:
        raise InstallerError("Public configuration has missing or unknown sections")
    stages = cloud["stages"]
    if not isinstance(stages, dict) or set(stages) != {"zfs", "boot_integrity", "k0s", "networking", "media", "intel_gpu", "postgres", "meilisearch", "stalwart", "tika", "bleve", "onlyoffice", "opencloud", "grist", "manticore", "redis_affine", "affine", "immich", "zabbix_server", "zabbix_agent", "logging", "notifications"}:
        raise InstallerError("Stage configuration is incomplete")
    if any(type(value) is not bool for value in stages.values()):
        raise InstallerError("Every stage flag must be Boolean")
    if stages["k0s"] and not stages["networking"]:
        raise InstallerError("Networking is mandatory whenever k0s is enabled")
    dependencies = load_yaml(SERVICE_CATALOG).get("private_cloud_stage_dependencies")
    if not isinstance(dependencies, dict) or set(dependencies) != set(stages) - {"zfs"}:
        raise InstallerError("Service catalog stage dependencies are incomplete")
    if any(not isinstance(required, list) or any(dependency not in stages for dependency in required) for required in dependencies.values()):
        raise InstallerError("Service catalog stage dependencies are invalid")
    if any(stages[stage] and not all(stages[dependency] for dependency in required) for stage, required in dependencies.items()):
        raise InstallerError("Enabled stages must follow the dependency chain")
    storage = cloud["storage"]
    if not isinstance(storage, dict) or set(storage) != {"disks", "arc_max"}:
        raise InstallerError("Storage configuration has missing or unknown keys")
    if not RAM_PATTERN.fullmatch(str(storage.get("arc_max", ""))) or ram_to_bytes(storage["arc_max"]) < 268435456:
        raise InstallerError("storage.arc_max must be at least 256Mi")
    disks = storage.get("disks") if isinstance(storage, dict) else None
    if not isinstance(disks, list) or any(not isinstance(disk, str) for disk in disks):
        raise InstallerError("storage.disks must be a list of paths")
    if stages["zfs"]:
        if len(disks) < 2 or len(set(disks)) != len(disks):
            raise InstallerError("At least two unique disks are required for ZFS")
        if any(not re.fullmatch(r"/dev/disk/by-(?:id|path)/[A-Za-z0-9_.:+-]+", disk) for disk in disks):
            raise InstallerError("ZFS disks must use stable /dev/disk/by-id or /dev/disk/by-path paths")
    k0s = cloud["k0s"]
    if not isinstance(k0s, dict) or set(k0s) != {"config_quota", "images_quota", "ephemeral_quota", "host_reserve_ram"}:
        raise InstallerError("k0s configuration has missing or unknown keys")
    for key in ("config_quota", "images_quota", "ephemeral_quota"):
        if not isinstance(k0s, dict) or not isinstance(k0s.get(key), str) or not k0s[key]:
            raise InstallerError(f"Missing k0s.{key}")
    for key in ("config_quota", "images_quota", "ephemeral_quota"):
        if not QUOTA_PATTERN.fullmatch(k0s[key]):
            raise InstallerError(f"Invalid k0s.{key}")
    if not RAM_PATTERN.fullmatch(str(k0s.get("host_reserve_ram", ""))) or ram_to_bytes(k0s["host_reserve_ram"]) < ram_to_bytes(storage["arc_max"]) + 1073741824:
        raise InstallerError("k0s.host_reserve_ram must cover ZFS ARC and at least 1Gi for host services")
    networking = cloud["networking"]
    expected_networking = {"storage_size", "acme_email", "cloudflare_zone_id", "public_ip_url", "managed_records", "pod_cidr", "service_cidr", "cluster_dns_ip", "local_network_cidrs", "traefik_internal_ip", "traefik_cluster_ip", "lan_dns_cluster_ip", "zabbix_hostname", "homepage_hostname", "lan_only_records", "amneziawg"}
    if not isinstance(networking, dict) or set(networking) != expected_networking:
        raise InstallerError("Networking configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(networking.get("storage_size", ""))):
        raise InstallerError("Invalid networking.storage_size")
    if not EMAIL_PATTERN.fullmatch(str(networking.get("acme_email", ""))):
        raise InstallerError("Invalid networking.acme_email")
    if not DOMAIN_PATTERN.fullmatch(str(networking.get("zabbix_hostname", ""))):
        raise InstallerError("Invalid networking.zabbix_hostname")
    if not DOMAIN_PATTERN.fullmatch(str(networking.get("homepage_hostname", ""))):
        raise InstallerError("Invalid networking.homepage_hostname")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", str(networking.get("cloudflare_zone_id", ""))):
        raise InstallerError("Invalid networking.cloudflare_zone_id")
    if not re.fullmatch(r"https://[^\s/]+(?:/[^\s]*)?", str(networking.get("public_ip_url", ""))):
        raise InstallerError("Invalid networking.public_ip_url")
    managed_records = networking.get("managed_records")
    if not isinstance(managed_records, list) or (stages["networking"] and not managed_records) or len(managed_records) != len(set(managed_records)):
        raise InstallerError("Cloudflare managed records must be a non-empty unique list")
    if any(not isinstance(record, str) or not DOMAIN_PATTERN.fullmatch(record) for record in managed_records):
        raise InstallerError("Invalid Cloudflare managed record")
    try:
        pod_network = ipaddress.ip_network(networking["pod_cidr"], strict=True)
        service_network = ipaddress.ip_network(networking["service_cidr"], strict=True)
        cluster_dns_address = ipaddress.ip_address(networking["cluster_dns_ip"])
        traefik_address = ipaddress.ip_address(networking["traefik_internal_ip"])
        fixed_cluster_addresses = [ipaddress.ip_address(networking[key]) for key in ("lan_dns_cluster_ip", "traefik_cluster_ip")]
        local_networks = [ipaddress.ip_network(value, strict=True) for value in networking["local_network_cidrs"]]
    except (KeyError, TypeError, ValueError) as error:
        raise InstallerError("Invalid networking address or CIDR") from error
    if not local_networks or pod_network.version != 4 or service_network.version != 4 or cluster_dns_address.version != 4 or traefik_address.version != 4 or any(value.version != 4 for value in local_networks):
        raise InstallerError("Networking currently requires IPv4 addresses")
    if cluster_dns_address not in service_network:
        raise InstallerError("The cluster DNS address must belong to the service CIDR")
    dns_offset = 10 if service_network.max_prefixlen - service_network.prefixlen > 3 else 2
    if cluster_dns_address != service_network.network_address + dns_offset:
        raise InstallerError("The cluster DNS address must be the address k0s derives from the service CIDR")
    if any(address not in service_network or address == service_network.broadcast_address for address in fixed_cluster_addresses):
        raise InstallerError("The service CIDR has no room for the LAN DNS and Traefik cluster addresses")
    if pod_network.overlaps(service_network) or any(network.overlaps(pod_network) or network.overlaps(service_network) for network in local_networks):
        raise InstallerError("Pod, service, and local network ranges must not overlap")
    if not any(traefik_address in network for network in local_networks):
        raise InstallerError("The Traefik host address must belong to a local network")
    if traefik_address in pod_network or traefik_address in service_network:
        raise InstallerError("Pod, service, and Traefik address ranges must not overlap")
    amneziawg = networking.get("amneziawg")
    if not isinstance(amneziawg, dict) or set(amneziawg) != {"hostname", "ui_hostname", "admin_username", "storage_size", "tunnel_cidr", "listen_port", "dns", "lan_access"}:
        raise InstallerError("AmneziaWG configuration has missing or unknown keys")
    for key in ("hostname", "ui_hostname"):
        if not DOMAIN_PATTERN.fullmatch(str(amneziawg.get(key, ""))):
            raise InstallerError(f"Invalid networking.amneziawg.{key}")
    if networking.get("lan_only_records") != [amneziawg["ui_hostname"]] + ([cloud["media"].get(key) for key in MEDIA_LAN_HOSTNAMES] if stages["media"] else []):
        raise InstallerError("networking.lan_only_records must list the AmneziaWG UI and enabled media LAN hostnames")
    if set(networking["lan_only_records"]) & set(managed_records):
        raise InstallerError("LAN-only hostnames must stay out of public DNS records")
    if not isinstance(amneziawg["admin_username"], str) or not USERNAME_PATTERN.fullmatch(amneziawg["admin_username"]):
        raise InstallerError("Invalid networking.amneziawg.admin_username")
    if not QUOTA_PATTERN.fullmatch(str(amneziawg["storage_size"])):
        raise InstallerError("Invalid networking.amneziawg.storage_size")
    try:
        tunnel_network = ipaddress.ip_network(amneziawg["tunnel_cidr"], strict=True)
    except (TypeError, ValueError) as error:
        raise InstallerError("Invalid AmneziaWG tunnel CIDR") from error
    if tunnel_network.version != 4 or tunnel_network.num_addresses < 4:
        raise InstallerError("The AmneziaWG tunnel must be an IPv4 network with room for peers")
    if tunnel_network.overlaps(pod_network) or tunnel_network.overlaps(service_network) or any(tunnel_network.overlaps(network) for network in local_networks):
        raise InstallerError("The AmneziaWG tunnel must not overlap cluster or local networks")
    if type(amneziawg.get("listen_port")) is not int or not 1 <= amneziawg["listen_port"] <= 65535:
        raise InstallerError("Invalid AmneziaWG listen port")
    if not isinstance(amneziawg["dns"], list) or not amneziawg["dns"]:
        raise InstallerError("AmneziaWG peers need at least one DNS server")
    for server in amneziawg["dns"]:
        try:
            address = ipaddress.IPv4Address(server)
        except (TypeError, ValueError) as error:
            raise InstallerError("Invalid AmneziaWG DNS server") from error
        if not any(address in network for network in local_networks):
            raise InstallerError("AmneziaWG DNS servers must belong to a local network for split DNS")
    if not isinstance(amneziawg["lan_access"], list):
        raise InstallerError("AmneziaWG LAN access must be a list")
    for rule in amneziawg["lan_access"]:
        try:
            destination = ipaddress.ip_network(rule["destination"], strict=True)
        except (KeyError, TypeError, ValueError) as error:
            raise InstallerError("Invalid AmneziaWG LAN destination") from error
        if set(rule) != {"destination", "protocol", "port"} or destination.version != 4:
            raise InstallerError("Invalid AmneziaWG LAN rule")
        if not any(destination.subnet_of(network) for network in local_networks):
            raise InstallerError("AmneziaWG LAN destinations must belong to a local network")
        if rule["protocol"] not in {"TCP", "UDP"} or type(rule["port"]) is not int or not 1 <= rule["port"] <= 65535:
            raise InstallerError("Invalid AmneziaWG LAN protocol or port")
    media = cloud["media"]
    if not isinstance(media, dict) or set(media) != {"storage_size", "hostname", "radarr_hostname", "prowlarr_hostname", "bazarr_hostname", "timezone", "quality_profiles", "vpn", "max_ram", "jellyfin_admin_username"}:
        raise InstallerError("Media configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(media.get("storage_size", ""))) or not DOMAIN_PATTERN.fullmatch(str(media.get("hostname", ""))):
        raise InstallerError("Invalid media storage size or hostname")
    for key in MEDIA_LAN_HOSTNAMES:
        if not DOMAIN_PATTERN.fullmatch(str(media[key])):
            raise InstallerError(f"Invalid media.{key}")
    if not isinstance(media["jellyfin_admin_username"], str) or not USERNAME_PATTERN.fullmatch(media["jellyfin_admin_username"]):
        raise InstallerError("Invalid media.jellyfin_admin_username")
    if quota_to_bytes(media["storage_size"]) <= 2 * 1024 ** 3:
        raise InstallerError("Media dataset quota must exceed 2GiB for Jellyfin startup")
    if not isinstance(media.get("timezone"), str) or not re.fullmatch(r"[A-Za-z_+-]+/[A-Za-z_+/-]+", media["timezone"]):
        raise InstallerError("Invalid media.timezone")
    media_memory = media.get("max_ram")
    if not isinstance(media_memory, dict) or set(media_memory) != {"sonarr", "radarr", "prowlarr", "qbittorrent", "jellyfin", "vpn_gateway", "vpn_route", "dns", "file_logs"}:
        raise InstallerError("Media memory configuration is incomplete")
    if any(not RAM_PATTERN.fullmatch(str(value)) or ram_to_bytes(value) < 33554432 for value in media_memory.values()):
        raise InstallerError("Every media memory limit must be at least 32Mi")
    quality_profiles = media.get("quality_profiles")
    if not isinstance(quality_profiles, dict) or set(quality_profiles) != {"sonarr", "radarr"}:
        raise InstallerError("Media quality profile configuration is incomplete")
    if any(value not in {"720p", "1080p", "2160p"} for value in quality_profiles.values()):
        raise InstallerError("Media quality profiles must be 720p, 1080p, or 2160p")
    vpn = media.get("vpn")
    if not isinstance(vpn, dict) or set(vpn) != {"gateway_cluster_ip", "server_countries", "endpoint_port", "peer_public_key", "address", "mtu", "dns", "persistent_keepalive"}:
        raise InstallerError("Media VPN configuration has missing or unknown keys")
    try:
        gateway_address = ipaddress.ip_address(vpn["gateway_cluster_ip"])
        tunnel_address = ipaddress.IPv4Interface(vpn["address"])
        tunnel_dns = ipaddress.IPv4Address(vpn["dns"])
    except (TypeError, ValueError) as error:
        raise InstallerError("Invalid media VPN address") from error
    if gateway_address in {ipaddress.ip_address(networking[key]) for key in ("cluster_dns_ip", "lan_dns_cluster_ip", "traefik_cluster_ip")}:
        raise InstallerError("The media VPN gateway must not reuse the cluster DNS, LAN DNS, or Traefik cluster address")
    if gateway_address not in service_network:
        raise InstallerError("The media VPN gateway must use the service CIDR")
    if "/" not in vpn["address"] or not tunnel_address.ip.is_private:
        raise InstallerError("The media VPN address must be a private IPv4 interface address with a prefix length")
    reserved_vpn_networks = [pod_network, service_network, tunnel_network, *local_networks]
    if not tunnel_dns.is_private or any(address in network for address in (tunnel_address.ip, tunnel_dns) for network in reserved_vpn_networks):
        raise InstallerError("The media VPN address and in-tunnel resolver must be private and must not overlap cluster, local, or AmneziaWG networks")
    countries = vpn.get("server_countries")
    if not isinstance(countries, list) or not countries or any(not isinstance(value, str) or not COUNTRY_PATTERN.fullmatch(value) for value in countries):
        raise InstallerError("Media VPN server_countries must list AirVPN country names")
    if vpn.get("endpoint_port") not in AIRVPN_WIREGUARD_PORTS or type(vpn["endpoint_port"]) is not int:
        raise InstallerError("Media VPN endpoint_port must be an AirVPN WireGuard port: 1637 or 47107")
    if not isinstance(vpn.get("peer_public_key"), str) or not WIREGUARD_KEY_PATTERN.fullmatch(vpn["peer_public_key"]):
        raise InstallerError("Invalid media VPN peer public key")
    if type(vpn.get("mtu")) is not int or not 1280 <= vpn["mtu"] <= 1420:
        raise InstallerError("Media VPN mtu must be between 1280 and 1420")
    if type(vpn.get("persistent_keepalive")) is not int or not 0 <= vpn["persistent_keepalive"] <= 65535:
        raise InstallerError("Media VPN persistent_keepalive must be between 0 and 65535 seconds")
    if media["hostname"] in {networking["zabbix_hostname"], configuration["private_cloud"]["stalwart"]["hostname"]}:
        raise InstallerError("Media hostname must be unique")
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
    expected_opencloud = {"storage_size", "max_ram", "hostname", "admin_email"}
    if not isinstance(opencloud, dict) or set(opencloud) != expected_opencloud:
        raise InstallerError("OpenCloud configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(opencloud.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(opencloud.get("max_ram", ""))):
        raise InstallerError("Invalid OpenCloud size configuration")
    if not isinstance(opencloud.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(opencloud["hostname"]):
        raise InstallerError("Invalid opencloud.hostname")
    if not EMAIL_PATTERN.fullmatch(str(opencloud["admin_email"])):
        raise InstallerError("Invalid opencloud.admin_email")
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
    expected_affine = {"storage_size", "max_ram", "hostname", "admin_email"}
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
    if not EMAIL_PATTERN.fullmatch(str(affine["admin_email"])):
        raise InstallerError("Invalid affine.admin_email")
    immich = cloud["immich"]
    expected_immich = {"storage_size", "hostname", "timezone", "max_ram", "machine_learning_max_ram", "machine_learning_accelerator", "valkey_max_ram", "admin_email"}
    if not isinstance(immich, dict) or set(immich) != expected_immich:
        raise InstallerError("Immich configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(immich.get("storage_size", ""))):
        raise InstallerError("Invalid immich.storage_size")
    for key in ("max_ram", "machine_learning_max_ram", "valkey_max_ram"):
        if not RAM_PATTERN.fullmatch(str(immich.get(key, ""))):
            raise InstallerError(f"Invalid immich.{key}")
    if ram_to_bytes(immich["max_ram"]) < 2147483648 or ram_to_bytes(immich["machine_learning_max_ram"]) < 1073741824 or ram_to_bytes(immich["valkey_max_ram"]) < 134217728:
        raise InstallerError("Immich memory limits are too small")
    if immich.get("machine_learning_accelerator") not in {"cpu", "openvino"}:
        raise InstallerError("Invalid immich.machine_learning_accelerator")
    if immich["machine_learning_accelerator"] == "openvino" and not stages["intel_gpu"]:
        raise InstallerError("Immich OpenVINO acceleration requires the Intel GPU stage")
    if not isinstance(immich.get("timezone"), str) or not re.fullmatch(r"[A-Za-z_+-]+/[A-Za-z_+/-]+", immich["timezone"]):
        raise InstallerError("Invalid immich.timezone")
    if not isinstance(immich.get("hostname"), str) or not DOMAIN_PATTERN.fullmatch(immich["hostname"]):
        raise InstallerError("Invalid immich.hostname")
    if not EMAIL_PATTERN.fullmatch(str(immich["admin_email"])):
        raise InstallerError("Invalid immich.admin_email")
    public_hostnames = [onlyoffice["hostname"], opencloud["hostname"], grist["hostname"], affine["hostname"], immich["hostname"]]
    if len(public_hostnames) != len(set(public_hostnames)):
        raise InstallerError("Every public application hostname must be unique")
    stalwart = cloud["stalwart"]
    expected_stalwart = {
        "storage_size", "max_ram", "domain", "hostname",
        "acme_contact", "admin_username", "mailbox_username", "relay_host", "relay_port", "relay_implicit_tls", "relay_username",
    }
    if not isinstance(stalwart, dict) or set(stalwart) != expected_stalwart:
        raise InstallerError("Stalwart configuration has missing or unknown keys")
    if not QUOTA_PATTERN.fullmatch(str(stalwart.get("storage_size", ""))) or not RAM_PATTERN.fullmatch(str(stalwart.get("max_ram", ""))):
        raise InstallerError("Invalid Stalwart size configuration")
    for key in ("domain", "hostname", "relay_host"):
        if not isinstance(stalwart.get(key), str) or not DOMAIN_PATTERN.fullmatch(stalwart[key]):
            raise InstallerError(f"Invalid stalwart.{key}")
    if stalwart["hostname"] == stalwart["domain"] or not stalwart["hostname"].endswith("." + stalwart["domain"]):
        raise InstallerError("Stalwart hostname must be a subdomain of domain")
    if stalwart["relay_host"].count(".") < 2:
        raise InstallerError("Stalwart relay_host must be a host inside the provider domain, such as mail.inbox.eu")
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
    logging = cloud["logging"]
    logging_keys = {"hostname", "openobserve_storage_size", "alloy_storage_size", "openobserve_max_ram", "alloy_max_ram", "retention_days"}
    if not isinstance(logging, dict) or set(logging) != logging_keys:
        raise InstallerError("Logging configuration has missing or unknown keys")
    if not DOMAIN_PATTERN.fullmatch(str(logging["hostname"])):
        raise InstallerError("Invalid logging.hostname")
    for service, minimum in (("openobserve", 1073741824), ("alloy", 268435456)):
        if not QUOTA_PATTERN.fullmatch(str(logging[service + "_storage_size"])):
            raise InstallerError(f"Invalid logging.{service}_storage_size")
        value = logging[service + "_max_ram"]
        if not RAM_PATTERN.fullmatch(str(value)) or ram_to_bytes(value) < minimum:
            raise InstallerError(f"Invalid logging.{service}_max_ram")
    if type(logging["retention_days"]) is not int or not 3 <= logging["retention_days"] <= 365:
        raise InstallerError("Logging retention_days must be between 3 and 365")
    notifications = cloud["notifications"]
    if not isinstance(notifications, dict) or set(notifications) != {"from_address"} or not EMAIL_PATTERN.fullmatch(str(notifications["from_address"])):
        raise InstallerError("Invalid notifications.from_address")
    boot_integrity = cloud["boot_integrity"]
    validate_boot_integrity(boot_integrity)
    public_hostnames = {
        "logging": logging["hostname"],
        "networking": amneziawg["hostname"],
        "media": media["hostname"],
        "stalwart": stalwart["hostname"],
        "zabbix_server": networking["zabbix_hostname"],
        "onlyoffice": cloud["onlyoffice"]["hostname"],
        "opencloud": cloud["opencloud"]["hostname"],
        "grist": cloud["grist"]["hostname"],
        "affine": cloud["affine"]["hostname"],
        "immich": cloud["immich"]["hostname"],
    }
    enabled_hostnames = [hostname for stage, hostname in public_hostnames.items() if stages[stage]]
    if stages["networking"]:
        enabled_hostnames += [amneziawg["ui_hostname"], networking["homepage_hostname"]]
    if stages["media"]:
        enabled_hostnames += [media[key] for key in MEDIA_LAN_HOSTNAMES]
    if len(enabled_hostnames) != len(set(enabled_hostnames)):
        raise InstallerError("Enabled public service hostnames must be unique")
    missing_records = sorted(set(public_hostnames[stage] for stage in public_hostnames if stages[stage]) - set(managed_records))
    if missing_records:
        raise InstallerError(f"Cloudflare managed records are missing: {', '.join(missing_records)}")


def validate_boot_integrity(boot_integrity: Any) -> None:
    if not isinstance(boot_integrity, dict) or set(boot_integrity) != {"interface", "host_address", "gateway_ip", "extra_pcrs", "extra_drivers"}:
        raise InstallerError("Boot integrity configuration has missing or unknown keys")
    if not re.fullmatch(r"[a-z][a-z0-9]{0,14}", str(boot_integrity["interface"])):
        raise InstallerError("Invalid boot_integrity.interface")
    try:
        host = ipaddress.IPv4Interface(boot_integrity["host_address"])
        gateway = ipaddress.IPv4Address(boot_integrity["gateway_ip"])
    except (TypeError, ValueError) as error:
        raise InstallerError("Invalid boot_integrity.host_address or boot_integrity.gateway_ip") from error
    if "/" not in boot_integrity["host_address"] or gateway not in host.network or gateway == host.ip:
        raise InstallerError("The boot_integrity gateway must be another address in the host network")
    extra_pcrs = boot_integrity["extra_pcrs"]
    if not isinstance(extra_pcrs, list) or any(type(value) is not int or value not in {1, 5} for value in extra_pcrs) or len(set(extra_pcrs)) != len(extra_pcrs):
        raise InstallerError("boot_integrity.extra_pcrs must be a unique list drawn from 1 and 5")
    extra_drivers = boot_integrity["extra_drivers"]
    if not isinstance(extra_drivers, list) or any(not isinstance(value, str) or not re.fullmatch(r"[a-z0-9_]+", value) for value in extra_drivers):
        raise InstallerError("boot_integrity.extra_drivers must be a list of kernel module names")


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
    if "grist" in secrets_root and "oidc_client_secret" in secrets_root["grist"] and len(secrets_root["grist"]["oidc_client_secret"]) < 16:
        raise InstallerError("The Grist OIDC client secret must contain at least 16 characters")
    cookie_secret = secrets_root.get("grist", {}).get("oidc_cookie_secret")
    if cookie_secret is not None and (len(cookie_secret) != 32 or not cookie_secret.isascii()):
        raise InstallerError("The Grist OIDC cookie secret must contain exactly 32 ASCII characters")
    wopi_secret = secrets_root.get("opencloud", {}).get("wopi_secret")
    if wopi_secret is not None and len(wopi_secret) < 32:
        raise InstallerError("The OpenCloud WOPI secret must contain at least 32 characters")
    agent_psk = secrets_root.get("zabbix", {}).get("agent_psk")
    if agent_psk is not None and not re.fullmatch(r"[0-9a-f]{64}", agent_psk):
        raise InstallerError("The Zabbix agent PSK must be 64 lowercase hexadecimal characters")
    for section, key in sorted(ADMIN_PASSWORDS):
        password = secrets_root.get(section, {}).get(key)
        if password is None:
            continue
        if len(password) < ADMIN_PASSWORD_MINIMUM_LENGTH:
            raise InstallerError(f"The {section}.{key} value must contain at least {ADMIN_PASSWORD_MINIMUM_LENGTH} characters")
        if re.sub(r"[^a-z]", "", password.lower()) in VENDOR_DEFAULT_PASSWORDS:
            raise InstallerError(f"The {section}.{key} value must not be a known vendor default")
    affine_admin_password = secrets_root.get("affine", {}).get("admin_password")
    if affine_admin_password is not None and len(affine_admin_password) > AFFINE_PASSWORD_MAXIMUM_LENGTH:
        raise InstallerError(f"The affine.admin_password value must contain at most {AFFINE_PASSWORD_MAXIMUM_LENGTH} characters")
    if "affine" in secrets_root and "database_password" in secrets_root["affine"] and len(secrets_root["affine"]["database_password"]) < 16:
        raise InstallerError("The AFFiNE database password must contain at least 16 characters")
    if "affine" in secrets_root and "oidc_client_secret" in secrets_root["affine"] and len(secrets_root["affine"]["oidc_client_secret"]) < 16:
        raise InstallerError("The AFFiNE OIDC client secret must contain at least 16 characters")
    if "immich" in secrets_root and "database_password" in secrets_root["immich"] and len(secrets_root["immich"]["database_password"]) < 16:
        raise InstallerError("The Immich database password must contain at least 16 characters")
    if "immich" in secrets_root and "oidc_client_secret" in secrets_root["immich"] and len(secrets_root["immich"]["oidc_client_secret"]) < 16:
        raise InstallerError("The Immich OIDC client secret must contain at least 16 characters")
    networking_secrets = secrets_root.get("networking", {})
    if any(len(networking_secrets.get(key, "x" * 20)) < 20 for key in ("cloudflare_api_token", "cloudflare_ddns_api_token")):
        raise InstallerError("Each Cloudflare API token must contain at least 20 characters")
    media_secrets = secrets_root.get("media", {})
    if any(key in media_secrets and not WIREGUARD_KEY_PATTERN.fullmatch(media_secrets[key]) for key in ("wireguard_private_key", "wireguard_preshared_key")):
        raise InstallerError("The media WireGuard private and preshared keys must be base64 WireGuard keys")
    proxy_password = secrets_root.get("media", {}).get("proxy_password")
    if proxy_password is not None and not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", proxy_password):
        raise InstallerError("The media VPN proxy password must contain 16 to 64 URL-safe characters")
    certificate_token = secrets_root.get("stalwart", {}).get("certificate_dns_api_token")
    if certificate_token is not None and len(certificate_token) < 20:
        raise InstallerError("The Stalwart certificate DNS API token must contain at least 20 characters")
    admin_password = secrets_root.get("logging", {}).get("admin_password")
    if admin_password is not None and len(admin_password) < 32:
        raise InstallerError("OpenObserve administrator password must contain at least 32 characters")
    passphrase = secrets_root.get("storage", {}).get("encryption_passphrase")
    if passphrase is not None and not 8 <= len(passphrase.encode()) <= 512:
        raise InstallerError("The storage passphrase must contain 8 to 512 bytes")


def validate_secret_value(section: str, key: str, value: str) -> None:
    validate_secrets_configuration(
        {"secrets_schema_version": CURRENT_SECRETS_SCHEMA_VERSION, "private_cloud_secrets": {section: {key: value}}}, {}
    )


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
        result = subprocess.run(list(args), input=input_text, text=True, check=True, capture_output=True, env=command_environment)
        if stage in {"ansible-playbook", "validation"}:
            _write_command_log(args, result.stdout, result.stderr)
        return result
    except (OSError, subprocess.CalledProcessError) as error:
        stdout = getattr(error, "stdout", "") or ""
        stderr = getattr(error, "stderr", "") or ""
        log_path = _write_command_log(args, stdout, stderr)
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


def reject_immutable_changes(stored: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    previous = stored["private_cloud"]
    current = candidate["private_cloud"]
    disabled = sorted(stage for stage, enabled in previous["stages"].items() if enabled and not current["stages"][stage])
    if disabled:
        raise InstallerError(f"Stages enabled in the stored configuration cannot be disabled: {', '.join(disabled)}")
    changed = [key for key in IMMUTABLE_NETWORK_KEYS if previous["networking"][key] != current["networking"][key]]
    if changed:
        raise InstallerError(f"Cluster network values cannot change after installation: {', '.join(changed)}")


def load_create_intent() -> dict[str, Any] | None:
    if not CREATE_INTENT_FILE.exists() and not CREATE_INTENT_FILE.is_symlink():
        return None
    details = CREATE_INTENT_FILE.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or stat.S_IMODE(details.st_mode) != 0o600:
        raise InstallerError(f"Create intent must be a root-owned regular file with mode 0600: {CREATE_INTENT_FILE}")
    try:
        intent = json.loads(CREATE_INTENT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InstallerError(f"Cannot read create intent: {CREATE_INTENT_FILE}") from error
    if not isinstance(intent, dict) or set(intent) != {"pool", "topology", "disks"} or intent["pool"] != POOL_NAME or intent["topology"] != "raidz1":
        raise InstallerError(f"Invalid create intent: {CREATE_INTENT_FILE}")
    if not isinstance(intent["disks"], list) or any(not isinstance(disk, str) for disk in intent["disks"]):
        raise InstallerError(f"Invalid create intent: {CREATE_INTENT_FILE}")
    return intent


def record_create_intent(disks: Sequence[str]) -> None:
    intent = {"pool": POOL_NAME, "topology": "raidz1", "disks": list(disks)}
    atomic_write(CREATE_INTENT_FILE, json.dumps(intent, sort_keys=True) + "\n", 0o600)


def clear_create_intent() -> None:
    CREATE_INTENT_FILE.unlink(missing_ok=True)


def resumable_create_intent() -> dict[str, Any] | None:
    intent = load_create_intent()
    if intent is None or not pool_exists() or PUBLIC_CONFIGURATION.is_file():
        return None
    return intent


def require_resumable_pool(intent: Mapping[str, Any], disks: Sequence[str]) -> None:
    if list(intent["disks"]) != list(disks):
        raise InstallerError("Selected disks do not match the recorded create intent")
    run_command(["python3", str(STORAGE_CHECKS), "pool-layout", "--pool", POOL_NAME, "--disks", *disks])
    secure = subprocess.run(["zfs", "get", "-H", "-o", "value", "keystatus", f"{POOL_NAME}/secure"], check=False, capture_output=True, text=True)
    if secure.returncode == 0 and secure.stdout.strip() != "available":
        raise InstallerError(f"Load the {POOL_NAME}/secure key before resuming the interrupted installation")


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


def quota_to_bytes(value: str) -> int:
    return int(value[:-1]) * 1024 ** ("KMGTPE".index(value[-1]) + 1)


def ram_to_bytes(value: str) -> int:
    units = {"Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4}
    return int(value[:-2]) * units[value[-2:]]




def _write_command_log(args: Sequence[str], stdout: str, stderr: str) -> Path:
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
    failure_match = re.search(r"(?m)^(?:fatal: .*?FAILED! =>|failed: \[)", stdout)
    task_output = stdout[:failure_match.start()] if failure_match else stdout
    task_matches = re.findall(r"(?m)^TASK \[([^]]+)]", task_output)
    task = task_matches[-1] if task_matches else command
    inferred_stage = task.split(" : ", 1)[0] if " : " in task else stage or command
    failure_lines = re.findall(r"(?m)^(?:fatal: .*?FAILED!|failed: \[.*?) => (.+)$", stdout)
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


def _section(cloud: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = cloud
    for key in path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


class InstallerError(RuntimeError):
    """An expected installer failure."""
