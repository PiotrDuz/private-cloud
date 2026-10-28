#!/usr/bin/env python3
"""Follow the external inbox over IMAP IDLE and hand new messages to Stalwart as their original sender."""

import imaplib
import os
import smtplib
import time

from imap_fetch_helpers import ProxySMTP, edge_client, envelope_sender, examine, log, new_uids, read_state, write_state

IDLE_SECONDS = 300
RETRY_SECONDS = 60


def main():
    config = {key: os.environ[key] for key in ("IMAP_HOST", "IMAP_USERNAME", "IMAP_PASSWORD", "RECIPIENT", "RECEIVER_DOMAIN", "STATE_PATH")}
    while True:
        try:
            follow(config)
        except (OSError, EOFError, imaplib.IMAP4.error, smtplib.SMTPException) as error:
            log("retry", error=f"{type(error).__name__}: {error}")
            time.sleep(RETRY_SECONDS)


def follow(config):
    """Deliver every message newer than the stored UID, then wait in IDLE until the mailbox changes."""
    with imaplib.IMAP4_SSL(config["IMAP_HOST"], 993, timeout=IDLE_SECONDS + 60) as imap:
        imap.login(config["IMAP_USERNAME"], config["IMAP_PASSWORD"])
        uidvalidity, uidnext = examine(imap)
        state = read_state(config["STATE_PATH"])
        if state.get("uidvalidity") != uidvalidity:
            # The first start, or a rebuilt provider mailbox, begins after the newest message.
            state = {"uidvalidity": uidvalidity, "last_uid": uidnext - 1}
            log("start", uidvalidity=uidvalidity, last_uid=state["last_uid"])
        while True:
            for uid in new_uids(imap, state["last_uid"]):
                deliver(config, uid, fetch(imap, uid))
                state["last_uid"] = uid
                write_state(config["STATE_PATH"], state)
            write_state(config["STATE_PATH"], state)
            with imap.idle(duration=IDLE_SECONDS) as idler:
                for response, _ in idler:
                    if response == "EXISTS":
                        break


def fetch(imap, uid):
    status, data = imap.uid("fetch", str(uid), "(BODY.PEEK[])")
    if status != "OK" or not data or not isinstance(data[0], tuple):
        raise imaplib.IMAP4.error(f"Cannot fetch UID {uid}")
    return data[0][1]


def deliver(config, uid, raw):
    """Temporary failures raise so the UID is retried; permanent rejections are logged and skipped."""
    helo, address = edge_client(raw, config["RECEIVER_DOMAIN"])
    try:
        with ProxySMTP(address, helo) as smtp:
            smtp.sendmail(envelope_sender(raw), [config["RECIPIENT"]], raw)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as error:
        codes = [code for code, _ in error.recipients.values()] if isinstance(error, smtplib.SMTPRecipientsRefused) else [error.smtp_code]
        if min(codes) < 500:
            raise
        log("rejected", uid=uid, codes=codes)
        return
    log("delivered", uid=uid, client=address)


if __name__ == "__main__":
    main()
