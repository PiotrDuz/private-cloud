"""Send an alert test message and confirm its arrival through JMAP."""
import base64
import http.client
import json
import smtplib
import socket
import ssl
import time
import urllib.parse
from email.message import EmailMessage


SMTP_TIMEOUT = 20
JMAP_TIMEOUT = 20
DELIVERY_TIMEOUT = 180
DELIVERY_DELAY = 10


def send_test_message(config, marker):
    message = EmailMessage()
    message["From"] = config["sender"]
    message["To"] = config["recipient"]
    message["Subject"] = marker
    message.set_content("Private cloud alert delivery verification " + marker + "\n")
    if config["relay_implicit_tls"]:
        client = smtplib.SMTP_SSL(config["relay_host"], config["relay_port"], timeout=SMTP_TIMEOUT)
    else:
        client = smtplib.SMTP(config["relay_host"], config["relay_port"], timeout=SMTP_TIMEOUT)
    with client:
        if not config["relay_implicit_tls"]:
            client.starttls(context=ssl.create_default_context())
        client.login(config["relay_username"], config["relay_password"])
        client.send_message(message)


def wait_for_delivery(config, marker):
    deadline = time.monotonic() + DELIVERY_TIMEOUT
    while time.monotonic() < deadline:
        for account in config["accounts"]:
            try:
                session = session_document(config, account)
                if session is not None and message_received(config, account, session, marker):
                    return account
            except (OSError, http.client.HTTPException, ValueError):
                continue
        time.sleep(DELIVERY_DELAY)
    return None


def session_document(config, account):
    status, headers, body = request_json(config, account, "GET", "/.well-known/jmap")
    if status in (301, 302, 303, 307, 308):
        location = headers.get("location", "")
        path = urllib.parse.urlsplit(location).path or "/jmap/session"
        status, headers, body = request_json(config, account, "GET", path)
    if status != 200:
        return None
    return json.loads(body)


def message_received(config, account, session, marker):
    account_id = next(iter(session.get("primaryAccounts", {}).values()), None)
    if account_id is None:
        account_id = next(iter(session.get("accounts", {})), None)
    if account_id is None:
        return False
    path = urllib.parse.urlsplit(session.get("apiUrl", "")).path or "/jmap"
    payload = {
        "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
        "methodCalls": [["Email/query", {"accountId": account_id, "filter": {"subject": marker}, "limit": 5}, "query"]],
    }
    status, _, body = request_json(config, account, "POST", path, payload)
    if status != 200:
        return False
    for name, result, _ in json.loads(body).get("methodResponses", []):
        if name == "Email/query" and result.get("ids"):
            return True
    return False


def matching_message_count(config, marker):
    """Count messages whose subject contains a unique validation marker."""
    count = 0
    for account in config["accounts"]:
        try:
            session = session_document(config, account)
            if session is None:
                continue
            account_id = next(iter(session.get("primaryAccounts", {}).values()), None)
            if account_id is None:
                account_id = next(iter(session.get("accounts", {})), None)
            if account_id is None:
                continue
            path = urllib.parse.urlsplit(session.get("apiUrl", "")).path or "/jmap"
            payload = {
                "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
                "methodCalls": [["Email/query", {"accountId": account_id, "filter": {"subject": marker}, "limit": 20}, "query"]],
            }
            status, _, body = request_json(config, account, "POST", path, payload)
            if status != 200:
                continue
            for name, result, _ in json.loads(body).get("methodResponses", []):
                if name == "Email/query":
                    count = max(count, len(result.get("ids", [])))
        except (OSError, http.client.HTTPException, ValueError):
            continue
    return count


def request_json(config, account, method, path, payload=None):
    token = base64.b64encode((account + ":" + config["password"]).encode()).decode()
    headers = {
        "Authorization": "Basic " + token,
        "Accept": "application/json",
        "User-Agent": "private-cloud-alert-verifier",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    context = ssl.create_default_context()
    with socket.create_connection((config["address"], config["port"]), timeout=JMAP_TIMEOUT) as connection:
        with context.wrap_socket(connection, server_hostname=config["hostname"]) as secured:
            client = http.client.HTTPSConnection(config["hostname"], config["port"], timeout=JMAP_TIMEOUT)
            client.sock = secured
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            content = response.read(4 * 1024 * 1024).decode(errors="replace")
            return response.status, {name.lower(): value for name, value in response.getheaders()}, content
