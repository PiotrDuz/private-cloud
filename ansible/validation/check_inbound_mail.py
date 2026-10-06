#!/usr/bin/env python3
"""Check provider forwarding acceptance and reject anonymous SMTP relaying."""

import json
import smtplib
import sys

from mail_helpers import require_accepted

def main():
    config = json.load(sys.stdin)
    with smtplib.SMTP(config["address"], 25, timeout=15) as client:
        require_accepted(client.ehlo(), "SMTP greeting")
        require_accepted(client.mail(config["sender"]), "anonymous inbound sender")
        require_accepted(client.rcpt(config["recipient"]), "configured forwarding recipient")
        require_accepted(client.rset(), "SMTP reset")
        require_accepted(client.mail(config["sender"]), "relay probe sender")
        code, _ = client.rcpt("private-cloud-validation@external.invalid")
        if code < 500:
            raise RuntimeError("SMTP did not reject an anonymous external relay recipient")
    print(json.dumps({"inbound_recipient": True, "anonymous_relay_rejected": True}))


if __name__ == "__main__":
    main()
