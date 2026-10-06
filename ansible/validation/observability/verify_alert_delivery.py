#!/usr/bin/env python3
"""Send one alert test message and confirm its arrival in the Stalwart mailbox."""
import json
import sys
import uuid

from alert_delivery_helpers import remove_test_messages, send_test_message, wait_for_delivery


def main():
    config = json.load(sys.stdin)
    marker = "private-cloud-alert-test-" + uuid.uuid4().hex
    account = None
    try:
        send_test_message(config, marker)
        account = wait_for_delivery(config, marker)
        if account is None:
            raise RuntimeError("The alert test message did not arrive in the Stalwart mailbox: " + marker)
        print(json.dumps({"delivered": True, "account": account, "marker": marker}, separators=(",", ":")))
    finally:
        primary_exception = sys.exc_info()[1]
        try:
            remove_test_messages(config, marker, account)
        except Exception as error:
            if primary_exception:
                raise RuntimeError("SMTP validation failed and its test message could not be removed") from error
            raise


if __name__ == "__main__":
    main()
