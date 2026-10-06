"""TLS context that trusts only the distribution's Mozilla public root store."""

import ssl
from pathlib import Path


MOZILLA_ROOTS = Path("/usr/share/ca-certificates/mozilla")


def public_context():
    roots = "".join(path.read_text() for path in sorted(MOZILLA_ROOTS.glob("*.crt")))
    if not roots:
        raise RuntimeError(f"No Mozilla public roots found in {MOZILLA_ROOTS}")
    context = ssl.create_default_context(cadata=roots)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context
