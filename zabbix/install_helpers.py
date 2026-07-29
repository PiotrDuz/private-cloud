from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

from installer_helpers import (  # noqa: E402
    CommandRunner,
    InstallerError,
    read_os_release,
    require_commands,
    require_root,
    write_managed_file,
)


@dataclass(frozen=True)
class InstallConfig:
    server_active: str
    hostname: str
    psk_identity: str | None
    psk_file: Path
    allow_plaintext: bool
