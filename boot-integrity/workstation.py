#!/usr/bin/env python3
"""Workstation helper: creates the Secure Boot owner keys and signs the UKI built on the host.

Requires openssl, efitools, and sbsigntool on the workstation; the private keys never leave it.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

KEYS = ("PK", "KEK", "db")
SIGNER = {"PK": "PK", "KEK": "PK", "db": "KEK"}


def main() -> int:
    command, *arguments = sys.argv[1:]
    if command == "keys":
        create_keys(Path(arguments[0]))
        return 0
    if command == "sign":
        sign(Path(arguments[0]), Path(arguments[1]), Path(arguments[2]))
        return 0
    return 2


def create_keys(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    guid = uuid.uuid4()
    (directory / "guid.txt").write_text(f"{guid}\n")
    for name in KEYS:
        run(["openssl", "req", "-new", "-x509", "-newkey", "rsa:4096", "-sha256", "-days", "3650", "-nodes",
             "-subj", f"/CN=private-cloud {name}/", "-keyout", directory / f"{name}.key", "-out", directory / f"{name}.crt"])
        (directory / f"{name}.key").chmod(0o600)
        run(["cert-to-efi-sig-list", "-g", guid, directory / f"{name}.crt", directory / f"{name}.esl"])
        signer = SIGNER[name]
        run(["sign-efi-sig-list", "-k", directory / f"{signer}.key", "-c", directory / f"{signer}.crt", name,
             directory / f"{name}.esl", directory / f"{name}.auth"])


def sign(unsigned: Path, signed: Path, directory: Path) -> None:
    run(["sbsign", "--key", directory / "db.key", "--cert", directory / "db.crt", "--output", signed, unsigned])
    run(["sbverify", "--cert", directory / "db.crt", signed])


def run(arguments: list[object]) -> None:
    subprocess.run([str(argument) for argument in arguments], check=True)


if __name__ == "__main__":
    raise SystemExit(main())
