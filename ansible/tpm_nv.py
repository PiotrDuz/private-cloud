"""TPM 2.0 NV primitives shared by the installer and the host tripwire."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

STATE_HANDLE = "0x01500010"
RECORD_HANDLE = "0x01500011"
KEY_HANDLE = "0x01500012"
RECORD_SIZE = 128
KEY_SIZE = 64
PCR_BANK = "sha256"
MEASURED_PCR = 11
INVENTORY_PCR = 15
BASE_PCRS = (0, 2, 4, 7)
ARMED = b"\x01"
WIPED = b"\x00"
MISSING_HANDLE = "0x18B"


class TpmError(RuntimeError):
    """A TPM command failed."""


def state() -> str:
    """Return armed, wiped, or unenrolled."""
    result = tpm("tpm2_nvread", STATE_HANDLE, "-C", STATE_HANDLE, check=False)
    if result.returncode == 0:
        return "armed" if result.stdout == ARMED else "wiped"
    if MISSING_HANDLE in result.stderr.decode(errors="replace"):
        return "unenrolled"
    raise TpmError(f"Cannot read the unlock state: {result.stderr.decode(errors='replace').strip()}")


def set_state(armed: bool) -> None:
    tpm("tpm2_nvwrite", STATE_HANDLE, "-C", STATE_HANDLE, "-i-", input=ARMED if armed else WIPED)


def wipe() -> None:
    """Destroy the unattended unlock secret; the key goes first and the state last."""
    for handle, size in ((KEY_HANDLE, KEY_SIZE), (RECORD_HANDLE, RECORD_SIZE)):
        tpm("tpm2_nvwrite", handle, "-C", handle, "-i-", input=bytes(size), check=False)
    set_state(False)


def provision(record_policy: bytes, key_policy: bytes, record: bytes, key: bytes) -> None:
    """Replace every unlock index; the state stays wiped until the caller arms it."""
    for handle in (STATE_HANDLE, RECORD_HANDLE, KEY_HANDLE):
        tpm("tpm2_nvundefine", handle, "-C", "o", check=False)
    define(STATE_HANDLE, 1, "authread|authwrite")
    define(RECORD_HANDLE, RECORD_SIZE, "authwrite|policyread|read_stclear", record_policy)
    define(KEY_HANDLE, KEY_SIZE, "authwrite|policyread|read_stclear", key_policy)
    tpm("tpm2_nvwrite", RECORD_HANDLE, "-C", RECORD_HANDLE, "-i-", input=record.ljust(RECORD_SIZE, b"\0"))
    tpm("tpm2_nvwrite", KEY_HANDLE, "-C", KEY_HANDLE, "-i-", input=key.ljust(KEY_SIZE, b"\0"))
    set_state(False)


def read_pcr(index: int) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "pcr.bin"
        tpm("tpm2_pcrread", f"{PCR_BANK}:{index}", "-o", output)
        return output.read_bytes()


def policy_digest(pcrs: Mapping[int, bytes]) -> bytes:
    """Return the PolicyPCR digest that a read must satisfy for these expected PCR values."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        values, session, digest = root / "pcr.bin", root / "session.ctx", root / "policy.dig"
        values.write_bytes(b"".join(pcrs[index] for index in sorted(pcrs)))
        selection = f"{PCR_BANK}:" + ",".join(str(index) for index in sorted(pcrs))
        tpm("tpm2_startauthsession", "-S", session)
        try:
            tpm("tpm2_policypcr", "-S", session, "-l", selection, "-f", values, "-L", digest)
        finally:
            tpm("tpm2_flushcontext", session, check=False)
        return digest.read_bytes()


def inventory_pcr_value(measurement: bytes) -> bytes:
    """Return PCR 15 after one extend of a zeroed register."""
    return hashlib.sha256(bytes(32) + measurement).digest()


def define(handle: str, size: int, attributes: str, policy: bytes | None = None) -> None:
    with tempfile.TemporaryDirectory() as directory:
        arguments = ["tpm2_nvdefine", handle, "-C", "o", "-s", size, "-a", attributes]
        if policy is not None:
            policy_file = Path(directory) / "policy.dig"
            policy_file.write_bytes(policy)
            arguments += ["-L", policy_file]
        tpm(*arguments)


def tpm(*arguments: object, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run([str(argument) for argument in arguments], input=input, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise TpmError(f"{arguments[0]} failed: {result.stderr.decode(errors='replace').strip()}")
    return result
