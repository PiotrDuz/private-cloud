"""Deliver the mock provider's accepted mail to the installed local MTA."""

import smtplib


def deliver_message(cloud, sender, recipients, lines):
    domains = {cloud['stalwart']['domain'], cloud['stalwart']['forwarding_domain']}
    if not recipients or any(address.rpartition('@')[2] not in domains for address in recipients):
        raise ValueError('The local mock only delivers mail to configured mailbox domains')
    message = ('\r\n'.join(lines) + '\r\n').encode()
    with smtplib.SMTP('127.0.0.1', 25, timeout=20) as client:
        refused = client.sendmail(sender, recipients, message)
        if refused:
            raise RuntimeError('The installed MTA rejected a mock provider recipient')


def envelope_address(command):
    value = command.partition(':')[2].strip()
    if value.startswith('<') and '>' in value:
        return value[1:value.index('>')]
    raise ValueError('Invalid SMTP envelope address')
