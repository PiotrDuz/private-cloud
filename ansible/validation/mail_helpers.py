"""Shared assertions for live SMTP protocol checks."""


def require_accepted(reply, operation):
    code, _ = reply
    if not 200 <= code < 300:
        raise RuntimeError(f"{operation} failed with SMTP {code}")
