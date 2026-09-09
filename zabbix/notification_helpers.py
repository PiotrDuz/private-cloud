"""Managed notification actions and independent logging health items."""
from api_helpers import same


def configure_email(api, config):
    relay = config["relay"]
    media = {
        "name": "Private cloud Stalwart inbox", "type": 0, "status": 0,
        "smtp_server": relay["host"], "smtp_port": relay["port"],
        "smtp_helo": config["mail_hostname"], "smtp_email": config["from_address"],
        "smtp_security": 2 if relay["implicit_tls"] else 1,
        "smtp_verify_peer": 1, "smtp_verify_host": 1, "smtp_authentication": 1,
        "username": relay["username"], "passwd": relay["password"],
        "maxattempts": 10, "attempt_interval": "1m", "message_format": 0,
    }
    media_id = api.ensure("mediatype", "mediatypeid", media, {"output": "extend", "filter": {"name": [media["name"]]}})
    users = api.call("user.get", {"output": ["userid", "username"], "filter": {"username": [config["admin_username"]]}, "selectMedias": "extend"})
    if len(users) != 1:
        raise ValueError("The managed Zabbix administrator was not found")
    user = users[0]
    managed_media = {"mediatypeid": media_id, "sendto": [config["recipient"]], "active": 0, "severity": 60, "period": "1-7,00:00-24:00"}
    current = user.get("medias", [])
    desired = [preserve_media(item) for item in current if str(item["mediatypeid"]) != str(media_id)]
    existing_managed = [item for item in current if str(item["mediatypeid"]) == str(media_id)]
    if existing_managed:
        managed_media["mediaid"] = existing_managed[0]["mediaid"]
    desired.append(managed_media)
    if not same(current, desired):
        api.call("user.update", {"userid": user["userid"], "medias": desired})
        api.changed = True
    body = "Host: {HOST.NAME}\nProblem: {EVENT.NAME}\nSeverity: {EVENT.SEVERITY}\nEvent: {EVENT.ID}\nStarted: {EVENT.DATE} {EVENT.TIME}\nDetails: {EVENT.OPDATA}\n" + config["web_url"] + "/tr_events.php?triggerid={TRIGGER.ID}&eventid={EVENT.ID}"
    operation = {"operationtype": 0, "opmessage_usr": [{"userid": user["userid"]}], "opmessage": {"mediatypeid": media_id, "default_msg": 0, "subject": "[{EVENT.SEVERITY}] {EVENT.NAME}", "message": body}}
    recovery = {"operationtype": 0, "opmessage_usr": [{"userid": user["userid"]}], "opmessage": {"mediatypeid": media_id, "default_msg": 0, "subject": "[RESOLVED] {EVENT.NAME}", "message": body + "\nRecovered: {EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}"}}
    action = {
        "name": "Private cloud all warnings to Stalwart", "eventsource": 0, "status": 0,
        "esc_period": "1h", "pause_suppressed": 1,
        "filter": {"evaltype": 1, "conditions": [{"conditiontype": 0, "operator": 0, "value": config["group_id"]}, {"conditiontype": 4, "operator": 5, "value": "2"}]},
        "operations": [{**operation, "esc_step_from": 1, "esc_step_to": 0}],
        "recovery_operations": [recovery],
    }
    api.ensure("action", "actionid", action, {"output": "extend", "filter": {"name": [action["name"]]}, "selectFilter": "extend", "selectOperations": "extend", "selectRecoveryOperations": "extend"})


def configure_health(api, config):
    host_id = config["host_id"]
    host = config["host"]
    master = {"hostid": host_id, "name": "Logging and certificate health", "key_": "observability.health", "type": 7, "value_type": 4, "delay": "1m", "history": "1d", "status": 0}
    master_id = ensure_item(api, master)
    ensure_trigger(api, host_id, "Logging health collector stopped", 'nodata(/' + host + '/observability.health,5m)=1', 4)
    gauges = [
        ("openobserve_up", "OpenObserve unavailable"), ("alloy_up", "Alloy unhealthy"),
        ("heartbeat", "Host logs have not reached OpenObserve for five minutes"),
        ("metrics_up", "Logging metrics collection failed"),
    ]
    for field, title in gauges:
        key = "observability." + field
        dependent(api, host_id, master_id, key, title, "$." + field)
        ensure_trigger(api, host_id, title, 'max(/' + host + '/' + key + ',2m)=0', 4)
    key = "observability.openobserve_internal_warnings"
    dependent(api, host_id, master_id, key, "OpenObserve internal warning logs", "$.openobserve_internal_warnings")
    ensure_trigger(api, host_id, "OpenObserve emitted warning-or-higher logs", 'max(/' + host + '/' + key + ',5m)>0', 2)
    for field in ("alloy_retries", "alloy_dropped", "openobserve_ingest_errors", "openobserve_notifications_failed"):
        key = "observability." + field
        dependent(api, host_id, master_id, key, field.replace("_", " "), "$." + field, rate=True)
        ensure_trigger(api, host_id, field.replace("_", " ") + " increased", 'max(/' + host + '/' + key + ',5m)>0', 2)
    for certificate in config["certificates"]:
        name = certificate["name"]
        for metric in ("valid", "days"):
            key = 'observability.certificate.' + metric + '["' + name + '"]'
            dependent(api, host_id, master_id, key, name + " certificate " + metric, '$.certificates["' + name + '"]["' + metric + '"]')
        valid_key = 'observability.certificate.valid["' + name + '"]'
        days_key = 'observability.certificate.days["' + name + '"]'
        ensure_trigger(api, host_id, name + " certificate invalid or unreachable", 'max(/' + host + '/' + valid_key + ',2m)=0', 4)
        for days, severity in ((21, 2), (7, 4)):
            ensure_trigger(api, host_id, name + " certificate expires within " + str(days) + " days", 'last(/' + host + '/' + days_key + ')<' + str(days) + ' and last(/' + host + '/' + valid_key + ')=1', severity)


def dependent(api, host_id, master_id, key, name, path, rate=False):
    preprocessing = [{"type": 12, "params": path}]
    if rate:
        preprocessing.append({"type": 10, "params": ""})
    ensure_item(api, {"hostid": host_id, "name": name, "key_": key, "type": 18, "value_type": 0, "delay": "0", "history": "7d", "trends": "90d", "master_itemid": master_id, "preprocessing": preprocessing, "status": 0})


def ensure_item(api, desired):
    return api.ensure("item", "itemid", desired, {"output": "extend", "hostids": [desired["hostid"]], "filter": {"key_": [desired["key_"]]}, "selectPreprocessing": "extend"})


def ensure_trigger(api, host_id, title, expression, severity):
    desired = {"description": title, "expression": expression, "priority": severity, "status": 0}
    return api.ensure("trigger", "triggerid", desired, {"output": "extend", "hostids": [host_id], "filter": {"description": [title]}, "expandExpression": True})


def preserve_media(media):
    return {key: media[key] for key in ("mediaid", "mediatypeid", "sendto", "active", "severity", "period")}
