#!/usr/bin/env python3
"""Send one alert test message and confirm its arrival in the Stalwart mailbox."""
import json
import sys
import uuid

from alert_delivery_helpers import send_test_message, wait_for_delivery


def main():
    config = json.load(sys.stdin)
    marker = "private-cloud-alert-test-" + uuid.uuid4().hex
    send_test_message(config, marker)
    account = wait_for_delivery(config, marker)
    if account is None:
        raise RuntimeError("The alert test message did not arrive in the Stalwart mailbox: " + marker)
    print(json.dumps({"delivered": True, "account": account, "marker": marker}, separators=(",", ":")))


if __name__ == "__main__":
    main()
