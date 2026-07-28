#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly COLLECTOR_SOURCE="${SCRIPT_DIR}/zabbix-zfs-collector.py"
readonly COLLECTOR_TARGET="/usr/local/libexec/zabbix/zfs-collector.py"
readonly SMART_WRAPPER_SOURCE="${SCRIPT_DIR}/zabbix-smartctl-wrapper"
readonly SMART_WRAPPER_TARGET="/usr/local/libexec/zabbix/smartctl-wrapper"
readonly AGENT_CONFIG="/etc/zabbix/zabbix_agent2.conf"
readonly USERPARAM_CONFIG="/etc/zabbix/zabbix_agent2.d/zfs.conf"
readonly SMART_PLUGIN_CONFIG="/etc/zabbix/zabbix_agent2.d/plugins.d/smart.conf"
readonly SMART_SUDOERS_CONFIG="/etc/sudoers.d/zabbix-smartctl"
readonly SMARTCTL_PATH="/usr/sbin/smartctl"
readonly DEFAULT_PSK_FILE="/etc/zabbix/zabbix_agent2.psk"

SERVER_ACTIVE=""
HOST_NAME=""
PSK_IDENTITY=""
PSK_FILE="$DEFAULT_PSK_FILE"
ALLOW_PLAINTEXT=0

usage() {
    cat <<'EOF'
Usage:
  sudo ./zabbix-agent-setup.sh \
    --server-active HOST[:PORT] \
    --hostname ZABBIX_HOST_NAME \
    --psk-identity IDENTITY [--psk-file PATH]

  sudo ./zabbix-agent-setup.sh \
    --server-active HOST[:PORT] \
    --hostname ZABBIX_HOST_NAME \
    --allow-plaintext

The PSK mode creates a 256-bit key when --psk-file does not already exist.
Plaintext mode must be explicitly requested and is intended only for a trusted lab network.
EOF
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

while (($#)); do
    case "$1" in
        --server-active)
            (($# >= 2)) || fail "--server-active requires a value"
            SERVER_ACTIVE="$2"
            shift 2
            ;;
        --hostname)
            (($# >= 2)) || fail "--hostname requires a value"
            HOST_NAME="$2"
            shift 2
            ;;
        --psk-identity)
            (($# >= 2)) || fail "--psk-identity requires a value"
            PSK_IDENTITY="$2"
            shift 2
            ;;
        --psk-file)
            (($# >= 2)) || fail "--psk-file requires a value"
            PSK_FILE="$2"
            shift 2
            ;;
        --allow-plaintext)
            ALLOW_PLAINTEXT=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

((EUID == 0)) || fail "run this installer as root"
[[ -n "$SERVER_ACTIVE" ]] || fail "--server-active is required"
[[ -n "$HOST_NAME" ]] || fail "--hostname is required"
[[ -f "$COLLECTOR_SOURCE" ]] || fail "collector not found: $COLLECTOR_SOURCE"
[[ -f "$SMART_WRAPPER_SOURCE" ]] || fail "SMART wrapper not found: $SMART_WRAPPER_SOURCE"

if ((ALLOW_PLAINTEXT)); then
    [[ -z "$PSK_IDENTITY" ]] || fail "do not combine --allow-plaintext with --psk-identity"
else
    [[ -n "$PSK_IDENTITY" ]] || fail "use --psk-identity or explicitly use --allow-plaintext"
fi

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    [[ "${ID:-}" == "ubuntu" ]] || fail "this installer currently supports Ubuntu only"
fi

printf 'Installing Zabbix Agent 2, SMART support, and collector dependencies...\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    zabbix-agent2 python3 openssl smartmontools sudo

[[ -x "$SMARTCTL_PATH" ]] || fail "smartctl not found: $SMARTCTL_PATH"
command -v visudo >/dev/null || fail "visudo is required to validate SMART permissions"

temporary_sudoers="$(mktemp)"
temporary_smart_config="$(mktemp)"
temporary_config=""
trap 'rm -f -- "${temporary_sudoers:-}" "${temporary_smart_config:-}" "${temporary_config:-}"' EXIT

install -d -m 0755 /usr/local/libexec/zabbix
install -m 0755 -o root -g root "$SMART_WRAPPER_SOURCE" "$SMART_WRAPPER_TARGET"

# Agent 2 invokes the root-owned compatibility wrapper through non-interactive
# sudo. Restrict access to the three read/discovery forms used by the plugin.
printf '%s\n' \
    '# Managed by zabbix-agent-setup.sh.' \
    "zabbix ALL=(root) NOPASSWD: $SMART_WRAPPER_TARGET -a *, $SMART_WRAPPER_TARGET --scan *, $SMART_WRAPPER_TARGET -j -V" \
    >"$temporary_sudoers"
chmod 0440 "$temporary_sudoers"
visudo -cf "$temporary_sudoers" >/dev/null
install -m 0440 -o root -g root "$temporary_sudoers" "$SMART_SUDOERS_CONFIG"

install -d -m 0755 /etc/zabbix/zabbix_agent2.d/plugins.d
printf '%s\n' \
    '# Managed by zabbix-agent-setup.sh.' \
    "Plugins.Smart.Path=$SMART_WRAPPER_TARGET" \
    >"$temporary_smart_config"
install -m 0644 -o root -g root "$temporary_smart_config" "$SMART_PLUGIN_CONFIG"

install -m 0755 -o root -g root "$COLLECTOR_SOURCE" "$COLLECTOR_TARGET"
install -d -m 0755 /etc/zabbix/zabbix_agent2.d

cat >"$USERPARAM_CONFIG" <<EOF
# Managed by zabbix-agent-setup.sh.
UserParameter=zfs.metrics,$COLLECTOR_TARGET metrics
UserParameter=zfs.snapshots,$COLLECTOR_TARGET snapshots
EOF
chown root:root "$USERPARAM_CONFIG"
chmod 0644 "$USERPARAM_CONFIG"

[[ -f "$AGENT_CONFIG" ]] || fail "Agent 2 configuration not found: $AGENT_CONFIG"
if [[ ! -e "${AGENT_CONFIG}.pre-private-cloud" ]]; then
    cp -a "$AGENT_CONFIG" "${AGENT_CONFIG}.pre-private-cloud"
fi

if ! grep -Eq '^[[:space:]]*Include=/etc/zabbix/zabbix_agent2\.d/\*\.conf[[:space:]]*$' "$AGENT_CONFIG"; then
    printf '\nInclude=/etc/zabbix/zabbix_agent2.d/*.conf\n' >>"$AGENT_CONFIG"
fi

temporary_config="$(mktemp)"
awk '
    /^# BEGIN PRIVATE-CLOUD ZABBIX SETTINGS$/ { managed = 1; next }
    /^# END PRIVATE-CLOUD ZABBIX SETTINGS$/ { managed = 0; next }
    managed { next }
    /^[[:space:]]*(Server|ServerActive|Hostname|ListenIP|Timeout|TLSConnect|TLSAccept|TLSPSKIdentity|TLSPSKFile)=/ { next }
    { print }
' "$AGENT_CONFIG" >"$temporary_config"

{
    printf '\n# BEGIN PRIVATE-CLOUD ZABBIX SETTINGS\n'
    printf 'Server=127.0.0.1\n'
    printf 'ServerActive=%s\n' "$SERVER_ACTIVE"
    printf 'Hostname=%s\n' "$HOST_NAME"
    printf 'ListenIP=127.0.0.1\n'
    printf 'Timeout=30\n'
    if ((ALLOW_PLAINTEXT)); then
        printf 'TLSConnect=unencrypted\n'
        printf 'TLSAccept=unencrypted\n'
    else
        if [[ ! -e "$PSK_FILE" ]]; then
            psk_directory="$(dirname -- "$PSK_FILE")"
            if [[ ! -d "$psk_directory" ]]; then
                install -d -m 0750 -o root -g zabbix "$psk_directory"
            fi
            umask 077
            openssl rand -hex 32 >"$PSK_FILE"
        fi
        [[ ! -L "$PSK_FILE" ]] || fail "PSK path must not be a symbolic link: $PSK_FILE"
        [[ -f "$PSK_FILE" ]] || fail "PSK path is not a regular file: $PSK_FILE"
        psk_directory="$(dirname -- "$PSK_FILE")"
        [[ "$(stat -c %u "$psk_directory")" == "0" ]] || \
            fail "PSK directory must be owned by root: $psk_directory"
        psk_directory_mode="$(stat -c %a "$psk_directory")"
        (((8#$psk_directory_mode & 0022) == 0)) || \
            fail "PSK directory must not be group/world writable: $psk_directory"
        psk_value="$(<"$PSK_FILE")"
        [[ "$psk_value" =~ ^[[:xdigit:]]{64}$ ]] || \
            fail "PSK file must contain exactly 64 hexadecimal characters"
        unset psk_value
        chown root:zabbix "$PSK_FILE"
        chmod 0640 "$PSK_FILE"
        printf 'TLSConnect=psk\n'
        printf 'TLSAccept=psk\n'
        printf 'TLSPSKIdentity=%s\n' "$PSK_IDENTITY"
        printf 'TLSPSKFile=%s\n' "$PSK_FILE"
    fi
    printf '# END PRIVATE-CLOUD ZABBIX SETTINGS\n'
} >>"$temporary_config"

install -m 0644 -o root -g root "$temporary_config" "$AGENT_CONFIG"

printf 'Validating collectors as the zabbix service user...\n'
runuser -u zabbix -- "$COLLECTOR_TARGET" metrics | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data.get("error_count"):
    raise SystemExit("collector errors: " + "; ".join(data.get("errors", [])))
'
runuser -u zabbix -- "$COLLECTOR_TARGET" snapshots | python3 -c '
import json, sys
data = json.load(sys.stdin)
if data.get("error_count"):
    raise SystemExit("collector errors: " + "; ".join(data.get("errors", [])))
'

zabbix_agent2 -t zfs.metrics -c "$AGENT_CONFIG" >/dev/null
runuser -u zabbix -- sudo -n "$SMART_WRAPPER_TARGET" -j -V >/dev/null
smart_discovery_test="$(
    runuser -u zabbix -- zabbix_agent2 \
        -t smart.disk.discovery \
        -c "$AGENT_CONFIG"
)"
if [[ "$smart_discovery_test" == *ZBX_NOTSUPPORTED* ]]; then
    fail "SMART plugin validation failed: $smart_discovery_test"
fi
systemctl enable --now zabbix-agent2.service
systemctl restart zabbix-agent2.service

printf '\nZabbix Agent 2 is installed and active.\n'
printf 'Agent hostname: %s\n' "$HOST_NAME"
printf 'Active server: %s\n' "$SERVER_ACTIVE"
if ((ALLOW_PLAINTEXT)); then
    printf 'Transport security: plaintext (explicitly selected)\n'
else
    printf 'Transport security: TLS PSK\n'
    printf 'PSK identity: %s\n' "$PSK_IDENTITY"
    printf 'PSK file: %s\n' "$PSK_FILE"
    printf 'Retrieve the PSK for Zabbix host configuration with: sudo cat %q\n' "$PSK_FILE"
fi
printf 'Import zabbix-zfs-template.yaml into Zabbix and link it to this host.\n'
printf 'Link the built-in "SMART by Zabbix agent active 2" template to this host.\n'
if [[ "$smart_discovery_test" == *'[s|[]]' ]]; then
    printf 'Warning: SMART discovery returned no disks; virtual disks may not expose SMART data.\n' >&2
fi
