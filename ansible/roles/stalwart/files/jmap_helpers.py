"""Stalwart management calls over JMAP through a temporary Kubernetes port-forward."""
import base64
import http.client
import json

USING = ["urn:ietf:params:jmap:core", "urn:stalwart:jmap"]


def certificate_hostnames(address, credentials):
    responses = call(address, credentials, [
        ["x:Certificate/query", {}, "0"],
        ["x:Certificate/get", {
            "#ids": {"resultOf": "0", "name": "x:Certificate/query", "path": "/ids"},
            "properties": ["subjectAlternativeNames"],
        }, "1"],
    ])
    return {name for certificate in responses[1]["list"] for name in certificate["subjectAlternativeNames"]}


def domain_id(address, credentials, name):
    ids = call(address, credentials, [["x:Domain/query", {"filter": {"name": name}}, "0"]])[0]["ids"]
    if len(ids) != 1:
        raise RuntimeError(f"Stalwart has {len(ids)} domains named {name}")
    return ids[0]


def create_acme_renewal(address, credentials, domain):
    response = call(address, credentials, [
        ["x:Task/set", {"create": {"renewal": {"@type": "AcmeRenewal", "domainId": domain}}}, "0"],
    ])[0]
    if "renewal" not in response.get("created", {}):
        raise RuntimeError(f"Stalwart rejected the ACME renewal task: {response.get('notCreated')}")


def call(address, credentials, method_calls):
    token = base64.b64encode(f"{credentials['username']}:{credentials['password']}".encode()).decode()
    connection = http.client.HTTPConnection(*address, timeout=30)
    try:
        connection.request(
            "POST", "/jmap",
            body=json.dumps({"using": USING, "methodCalls": method_calls}),
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        text = response.read().decode(errors="replace")
    finally:
        connection.close()
    if response.status != 200:
        raise RuntimeError(f"Stalwart JMAP returned HTTP {response.status}")
    responses = json.loads(text)["methodResponses"]
    errors = [arguments for name, arguments, _ in responses if name == "error"]
    if errors:
        raise RuntimeError(f"Stalwart JMAP call failed: {errors[0]}")
    return [arguments for _, arguments, _ in responses]
