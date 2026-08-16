from __future__ import annotations

import getpass
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import ZABBIX_HOSTNAME  # noqa: E402

PROGRESS_CONTEXT_FIELDS = frozenset(
    ("hostname", "root_dataset", "server_node_port", "web_node_port")
)
Validator = Callable[[str], None]


def require_setup_environment(scripts: Sequence[Path]) -> None:
    if os.geteuid() != 0:
        raise SetupError("Run the setup app as root")
    if not sys.stdin.isatty():
        raise SetupError("An interactive terminal is required; allocate a TTY for SSH")
    for script in scripts:
        if not script.is_file():
            raise SetupError(f"Installer not found: {script}")


def load_setup_progress(
    path: Path,
    stage_names: Sequence[str],
) -> SetupProgress:
    if not path.exists():
        return SetupProgress()
    validate_progress_path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SetupError(f"Cannot read setup progress: {path}") from error
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise SetupError(f"Unsupported setup progress format: {path}")

    completed = payload.get("completed")
    current_stage = payload.get("current_stage")
    context = payload.get("context")
    allowed = set(stage_names)
    invalid_completed = (
        not isinstance(completed, list)
        or any(
            not isinstance(stage, str) or stage not in allowed
            for stage in completed
        )
        or len(completed) != len(set(completed))
    )
    invalid_current = current_stage is not None and (
        not isinstance(current_stage, str) or current_stage not in allowed
    )
    invalid_context = not isinstance(context, dict)
    if not invalid_context:
        invalid_context = any(
            not isinstance(key, str)
            or key not in PROGRESS_CONTEXT_FIELDS
            or not isinstance(value, str)
            for key, value in context.items()
        )
    if invalid_completed or invalid_current or invalid_context:
        raise SetupError(f"Invalid setup progress: {path}")
    if current_stage in completed:
        raise SetupError(f"Invalid setup progress: {path}")
    positions = [stage_names.index(stage) for stage in completed]
    if positions != sorted(positions):
        raise SetupError(f"Invalid setup progress order: {path}")
    return SetupProgress(completed, current_stage, context)


def save_setup_progress(path: Path, progress: SetupProgress) -> None:
    ensure_progress_directory(path.parent)
    content = json.dumps(
        {
            "completed": progress.completed,
            "context": progress.context,
            "current_stage": progress.current_stage,
            "version": 1,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        temporary_path.chmod(0o600)
        temporary_path.replace(path)
    except OSError as error:
        raise SetupError(f"Cannot save setup progress: {path}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def validate_progress_path(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise SetupError(f"Cannot inspect setup progress: {path}") from error
    if path.is_symlink() or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
        raise SetupError(f"Unsafe setup progress file: {path}")


def ensure_progress_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        metadata = path.lstat()
    except OSError as error:
        raise SetupError(f"Cannot prepare setup progress directory: {path}") from error
    if path.is_symlink() or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
        raise SetupError(f"Unsafe setup progress directory: {path}")


def begin_step(number: int, total: int, title: str, detail: str) -> bool:
    print(f"\n[{number}/{total}] {title}")
    print(detail)
    action = prompt_choice(
        "Choose an action",
        {"r": "run", "run": "run", "s": "skip", "skip": "skip", "q": "quit", "quit": "quit"},
        "run",
    )
    if action == "quit":
        raise SetupCancelled
    return action == "run"


def prompt_value(
    label: str,
    *,
    default: str | None = None,
    validator: Validator | None = None,
) -> str:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ").strip()
        if not value and default is not None:
            value = default
        try:
            if validator is not None:
                validator(value)
        except ValueError as error:
            print(f"Invalid value: {error}", file=sys.stderr)
            continue
        return value


def prompt_secret(label: str, *, confirm: bool = True) -> str:
    while True:
        first = getpass.getpass(f"{label}: ")
        if not first:
            print("The value cannot be empty", file=sys.stderr)
            continue
        if not confirm:
            return first
        second = getpass.getpass(f"Confirm {label.lower()}: ")
        if hmac.compare_digest(first, second):
            return first
        print("Values do not match", file=sys.stderr)


def prompt_choice(
    label: str,
    choices: Mapping[str, str],
    default: str,
) -> str:
    canonical = sorted(set(choices.values()))
    while True:
        value = input(f"{label} ({'/'.join(canonical)}) [{default}]: ").strip().lower()
        if not value:
            return default
        if value in choices:
            return choices[value]
        print("Choose one of the listed values", file=sys.stderr)


def review_configuration(
    title: str,
    values: Sequence[tuple[str, str]],
) -> str:
    print(f"\n{title} configuration:")
    for label, value in values:
        print(f"  {label}: {value}")
    return prompt_choice(
        "Choose an action",
        {
            "r": "run",
            "run": "run",
            "e": "edit",
            "edit": "edit",
            "s": "skip",
            "skip": "skip",
            "q": "quit",
            "quit": "quit",
        },
        "run",
    )


def resolve_review(action: str) -> bool | None:
    if action == "quit":
        raise SetupCancelled
    if action == "skip":
        return False
    if action == "run":
        return True
    return None


def run_installer(
    title: str,
    script: Path,
    *,
    arguments: Sequence[str] = (),
    environment: Mapping[str, str] | None = None,
) -> None:
    command = [sys.executable, str(script), *arguments]
    child_environment = os.environ.copy()
    if environment is not None:
        child_environment.update(environment)

    print(f"\nStarting {title}...")
    try:
        result = subprocess.run(
            command,
            cwd=PROJECT_DIRECTORY,
            env=child_environment,
            check=False,
        )
    finally:
        if environment is not None:
            for name in environment:
                child_environment.pop(name, None)
    if result.returncode != 0:
        raise InstallerFailure(title, result.returncode)
    print(f"{title} completed.")


def validate_dataset(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)+", value):
        raise ValueError("use a ZFS dataset such as tank/secure")


def validate_nonempty(value: str) -> None:
    if not value:
        raise ValueError("a value is required")
    if "\n" in value or "\r" in value:
        raise ValueError("line breaks are not allowed")


def validate_positive_integer(value: str) -> None:
    if not value.isdecimal() or int(value) < 1:
        raise ValueError("use a positive integer")


def validate_zfs_size(value: str) -> None:
    if not re.fullmatch(r"[1-9][0-9]*[KMGTPE]", value):
        raise ValueError("use a whole ZFS size such as 5G")


def validate_memory(value: str) -> None:
    match = re.fullmatch(r"([1-9][0-9]*)(Ki|Mi|Gi|Ti)", value)
    if match is None:
        raise ValueError("use a binary size such as 2Gi")
    multipliers = {"Ki": 1, "Mi": 1024, "Gi": 1024**2, "Ti": 1024**3}
    mebibytes = int(match.group(1)) * multipliers[match.group(2)] // 1024
    if mebibytes < 256:
        raise ValueError("PostgreSQL needs at least 256Mi")


def validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("use letters, digits, and underscores")


def validate_node_port(value: str) -> None:
    if not value.isdecimal() or not 30000 <= int(value) <= 32767:
        raise ValueError("use a port from 30000 through 32767")


def validate_server_address(value: str) -> None:
    if not re.fullmatch(r"[^\s,]+(?::\d{1,5})?", value):
        raise ValueError("use a hostname or address with an optional port")
    port = value.rsplit(":", 1)[-1]
    if port.isdecimal() and not 1 <= int(port) <= 65535:
        raise ValueError("the port must be from 1 through 65535")


def validate_absolute_path(value: str) -> None:
    if not Path(value).is_absolute():
        raise ValueError("use an absolute path")
    if "\n" in value or "\r" in value:
        raise ValueError("line breaks are not allowed")


@dataclass
class SetupProgress:
    completed: list[str] = field(default_factory=list)
    current_stage: str | None = None
    context: dict[str, str] = field(default_factory=dict)


class SetupError(RuntimeError):
    pass


class SetupCancelled(RuntimeError):
    pass


class InstallerFailure(SetupError):
    def __init__(self, title: str, returncode: int) -> None:
        super().__init__(f"{title} failed with exit code {returncode}")
        self.returncode = returncode
