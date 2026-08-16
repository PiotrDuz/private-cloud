from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

ZABBIX_HOSTNAME = "private-cloud-zabbix"


def require_root() -> None:
    if os.geteuid() != 0:
        raise InstallerError("Run this installer as root")


def require_commands(commands: Sequence[str]) -> None:
    for command in commands:
        if shutil.which(command) is None:
            raise InstallerError(f"Required command not found: {command}")


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def read_os_release() -> dict[str, str]:
    try:
        lines = Path("/etc/os-release").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InstallerError("Cannot identify this operating system") from error

    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip("\"'")
    return values


def write_managed_file(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        temporary_path.chmod(mode)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


class InstallerError(RuntimeError):
    pass


class CommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            command = " ".join(args)
            message = f"Command failed ({result.returncode}): {command}"
            if detail:
                message = f"{message}: {detail}"
            raise InstallerError(message)
        return result
