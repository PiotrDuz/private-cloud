"""Trigger a disposable ACME issuance and verify Stalwart serves the trusted leaf."""

import base64
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import smtplib
import ssl
import stat
import subprocess
import time
import urllib.parse


ARTIFACTS = Path("/var/lib/private-cloud-live-test")
NAMESPACE = "private-cloud"
SERVICE = "stalwart"
SERVICE_PORT = 8080
SMTP_PORT = 25
TASK_TIMEOUT = 240
TASK_POLL_INTERVAL = 2


def issue_stalwart_certificate(configuration):
    cloud = configuration["private_cloud"]
    stalwart = cloud["stalwart"]
    hostname = stalwart["hostname"].rstrip(".")
    address = cloud["networking"]["traefik_internal_ip"]
    if smtp_starttls_is_trusted(address, hostname):
        return {
            "service": SERVICE,
            "hostname": hostname,
            "certificate": "reused",
            "acme_renewal": "not_needed",
            "smtp_starttls": "trusted",
        }

    admin_name = stalwart["admin_username"]
    admin_account = admin_name if "@" in admin_name else admin_name + "@" + stalwart["domain"]
    password = read_service_password()
    service_ip = get_service_ip()
    authorization = "Basic " + base64.b64encode((admin_account + ":" + password).encode()).decode()
    client = JmapClient(service_ip, SERVICE_PORT, hostname, authorization)

    domain_id = find_tls_domain(client, hostname)
    before_certificates = acme_certificates()
    task_id = queue_renewal(client, domain_id)
    wait_for_renewal_and_tls(client, task_id, address, hostname, before_certificates)
    return {"service": SERVICE, "hostname": hostname, "acme_renewal": "completed", "smtp_starttls": "trusted"}


def read_service_password():
    path = ARTIFACTS / "credentials.json"
    try:
        metadata = path.lstat()
    except OSError as error:
        raise RuntimeError("The root-owned live-test credential artifact is missing") from error
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RuntimeError("The live-test credential artifact must be a private root-owned regular file")
    if not path.is_file():
        raise RuntimeError("The root-owned live-test credential artifact is missing")
    try:
        credentials = json.loads(path.read_text())
        password = credentials["service"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError("The live-test credential artifact has no Stalwart service password") from error
    if not isinstance(password, str) or not password:
        raise RuntimeError("The live-test Stalwart service password is empty")
    return password


def get_service_ip():
    result = subprocess.run(
        ["k0s", "kubectl", "get", "service", SERVICE, "--namespace", NAMESPACE, "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    service = json.loads(result.stdout)
    address = service.get("spec", {}).get("clusterIP")
    if not address or address == "None":
        raise RuntimeError("The Stalwart service has no cluster IP for the ACME fixture")
    return address


def find_tls_domain(client, hostname):
    result = client.call("x:Domain/query", {"filter": {"name": hostname}})
    ids = result.get("ids", [])
    if len(ids) != 1:
        raise RuntimeError("Stalwart does not contain exactly one configured TLS domain: " + hostname)
    domain = client.call("x:Domain/get", {"ids": ids, "properties": ["name", "certificateManagement"]})
    records = domain.get("list", [])
    if len(records) != 1 or records[0].get("name", "").rstrip(".") != hostname:
        raise RuntimeError("Stalwart returned an unexpected domain for the configured TLS hostname")
    management = records[0].get("certificateManagement", {})
    if management.get("@type") != "Automatic":
        raise RuntimeError("The configured Stalwart TLS domain is not set to automatic certificate management")
    return ids[0]


def queue_renewal(client, domain_id):
    due = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    result = client.call("x:Task/set", {
        "create": {
            "renewal": {
                "@type": "AcmeRenewal",
                "domainId": domain_id,
                "status": {"@type": "Pending", "due": due},
            }
        }
    })
    created = result.get("created", {}).get("renewal", {})
    task_id = created.get("id")
    if not task_id:
        details = result.get("notCreated", {}).get("renewal", {})
        raise RuntimeError("Stalwart rejected the ACME renewal task: " + json.dumps(details, sort_keys=True))
    return task_id


def wait_for_renewal_and_tls(client, task_id, address, hostname, previous_certificates):
    deadline = time.monotonic() + TASK_TIMEOUT
    task_completed = False
    tls_error = None
    while time.monotonic() < deadline:
        task = get_task(client, task_id)
        if task is None:
            task_completed = True
        elif task.get("status", {}).get("@type") == "Failed":
            reason = task["status"].get("failureReason", "no failure reason reported")
            raise RuntimeError("Stalwart ACME renewal failed: " + reason)

        if task_completed:
            issued = acme_certificates() - previous_certificates
            if issued:
                try:
                    verify_smtp_starttls(address, hostname)
                    return
                except (OSError, smtplib.SMTPException, ssl.SSLError) as error:
                    tls_error = error
        time.sleep(TASK_POLL_INTERVAL)

    if not task_completed:
        raise TimeoutError("Stalwart did not complete the ACME renewal task within the fixture timeout")
    if not acme_certificates() - previous_certificates:
        raise RuntimeError("The ACME mock did not issue a new certificate for the queued renewal")
    raise RuntimeError("Stalwart completed ACME renewal but SMTP STARTTLS did not serve the trusted certificate") from tls_error


def get_task(client, task_id):
    try:
        result = client.call("x:Task/get", {"ids": [task_id]})
    except RuntimeError as error:
        if "notFound" in str(error):
            return None
        raise
    records = result.get("list", [])
    if not records:
        return None
    return records[0]


def acme_certificates():
    return {path.name for path in ARTIFACTS.glob("*.crt") if path.name not in {"ca.crt", "server.crt", "client.crt"}}


def verify_smtp_starttls(address, hostname):
    with smtplib.SMTP(timeout=15) as client:
        client.connect(address, SMTP_PORT)
        client._host = hostname
        client.ehlo()
        if not client.has_extn("starttls"):
            raise RuntimeError("The configured Stalwart SMTP endpoint did not advertise STARTTLS")
        client.starttls(context=ssl.create_default_context())


def smtp_starttls_is_trusted(address, hostname):
    try:
        verify_smtp_starttls(address, hostname)
        return True
    except (OSError, RuntimeError, smtplib.SMTPException, ssl.SSLError):
        return False


class JmapClient:
    def __init__(self, address, port, hostname, authorization):
        self.address = address
        self.port = port
        self.hostname = hostname
        self.authorization = authorization
        self.api_path = self.discover_api_path()

    def discover_api_path(self):
        status, headers, body = self.request("GET", "/jmap/session")
        if status in (301, 302, 303, 307, 308):
            location = urllib.parse.urlsplit(headers.get("location", ""))
            path = location.path or "/jmap/session"
            status, headers, body = self.request("GET", path)
        if status != 200:
            raise RuntimeError("Stalwart JMAP discovery returned HTTP " + str(status))
        try:
            session = json.loads(body)
            api_url = urllib.parse.urlsplit(session["apiUrl"])
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise RuntimeError("Stalwart JMAP discovery returned an invalid session document") from error
        if not api_url.path:
            raise RuntimeError("Stalwart JMAP discovery did not provide an API path")
        return api_url.path

    def call(self, method, arguments):
        payload = {
            "using": ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"],
            "methodCalls": [[method, arguments, "validation"]],
        }
        status, _, body = self.request("POST", self.api_path, payload)
        if status != 200:
            raise RuntimeError(method + " returned HTTP " + str(status))
        try:
            responses = json.loads(body).get("methodResponses", [])
        except json.JSONDecodeError as error:
            raise RuntimeError(method + " returned invalid JMAP JSON") from error
        response = next((value for name, value, _ in responses if name == method), None)
        if response is None:
            errors = [value for name, value, _ in responses if name == "error"]
            raise RuntimeError(method + " failed: " + json.dumps(errors, sort_keys=True))
        return response

    def request(self, method, path, payload=None):
        headers = {"Authorization": self.authorization, "Host": self.hostname}
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":"))
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(self.address, self.port, timeout=20)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, response.read(4 * 1024 * 1024).decode(errors="replace")
        finally:
            connection.close()
