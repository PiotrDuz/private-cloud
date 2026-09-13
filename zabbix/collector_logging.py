"""Journal diagnostics shared by host-side Zabbix collectors."""

import syslog


def log_collector_errors(collector, errors):
    if not errors:
        return
    try:
        syslog.openlog(
            ident=f"private-cloud-zabbix-{collector}",
            logoption=syslog.LOG_PID,
            facility=syslog.LOG_DAEMON,
        )
        for error in dict.fromkeys(errors):
            message = str(error).replace("\x00", " ").replace("\n", " ").replace("\r", " ")[:4096]
            syslog.syslog(syslog.LOG_ERR, f"collector={collector} {message}")
    except Exception:
        pass
