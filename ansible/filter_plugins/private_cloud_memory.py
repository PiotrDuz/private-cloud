"""Use the installer's Kubernetes memory units in Ansible roles."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_helpers import ram_to_bytes


class FilterModule:
    def filters(self):
        return {"private_cloud_ram_bytes": ram_to_bytes}
