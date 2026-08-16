from __future__ import annotations

import re
import subprocess
from typing import Sequence

from installer_helpers import InstallerError

POSTGRES_DEPLOYMENT = "postgres"
POSTGRES_ADMIN_DATABASE = "postgres"
POSTGRES_ADMIN_USERNAME = "postgres"


def ensure_zabbix_database(
    namespace: str,
    database: str,
    username: str,
    password: str,
) -> None:
    validate_identifier(database, "database")
    validate_identifier(username, "username")
    validate_database_identity(database, username)
    if not password:
        raise InstallerError("Zabbix database password cannot be empty")

    ensure_role(namespace, username, password)
    if not database_exists(namespace, database):
        run_postgres_command(
            namespace,
            [
                "createdb",
                "-U",
                POSTGRES_ADMIN_USERNAME,
                "-O",
                username,
                database,
            ],
        )
    set_database_owner(namespace, database, username)
    validate_database(namespace, database, username)


def ensure_role(namespace: str, username: str, password: str) -> None:
    quoted_username = sql_identifier(username)
    script = f"""DO $private_cloud$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = {sql_literal(username)}) THEN
        ALTER ROLE {quoted_username} WITH LOGIN PASSWORD {sql_literal(password)};
    ELSE
        CREATE ROLE {quoted_username} WITH LOGIN PASSWORD {sql_literal(password)};
    END IF;
END
$private_cloud$;
"""
    run_psql(namespace, script, sensitive=True)


def database_exists(namespace: str, database: str) -> bool:
    result = run_postgres_command(
        namespace,
        [
            "psql",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            POSTGRES_ADMIN_USERNAME,
            "-d",
            POSTGRES_ADMIN_DATABASE,
            "-c",
            f"SELECT 1 FROM pg_database WHERE datname = {sql_literal(database)};",
        ],
    )
    return result.stdout.strip() == "1"


def set_database_owner(namespace: str, database: str, username: str) -> None:
    run_psql(
        namespace,
        f"ALTER DATABASE {sql_identifier(database)} "
        f"OWNER TO {sql_identifier(username)};\n",
    )


def validate_database(namespace: str, database: str, username: str) -> None:
    query = (
        "SELECT r.rolcanlogin, pg_get_userbyid(d.datdba) "
        "FROM pg_database d JOIN pg_roles r ON r.rolname = "
        f"{sql_literal(username)} WHERE d.datname = {sql_literal(database)};"
    )
    result = run_postgres_command(
        namespace,
        [
            "psql",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            POSTGRES_ADMIN_USERNAME,
            "-d",
            POSTGRES_ADMIN_DATABASE,
            "-c",
            query,
        ],
    )
    if result.stdout.strip() != f"t|{username}":
        raise InstallerError("Zabbix PostgreSQL database or login role is invalid")


def run_psql(
    namespace: str,
    script: str,
    *,
    sensitive: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run_postgres_command(
        namespace,
        [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            POSTGRES_ADMIN_USERNAME,
            "-d",
            POSTGRES_ADMIN_DATABASE,
        ],
        input_text=script,
        sensitive=sensitive,
    )


def run_postgres_command(
    namespace: str,
    command: Sequence[str],
    *,
    input_text: str | None = None,
    sensitive: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = ["k0s", "kubectl", "-n", namespace, "exec"]
    if input_text is not None:
        arguments.append("-i")
    arguments.extend([f"deployment/{POSTGRES_DEPLOYMENT}", "--", *command])
    try:
        result = subprocess.run(
            arguments,
            input=input_text,
            text=True,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise InstallerError("Unable to configure the Zabbix PostgreSQL database") from error
    if result.returncode != 0:
        message = "Zabbix PostgreSQL database configuration failed"
        if not sensitive:
            detail = result.stderr.strip() or result.stdout.strip()
            if detail:
                message = f"{message}: {detail}"
        raise InstallerError(message)
    return result


def validate_database_identity(database: str, username: str) -> None:
    if database.lower() in {"postgres", "template0", "template1"}:
        raise InstallerError("Zabbix cannot use a PostgreSQL system database")
    normalized_username = username.lower()
    if normalized_username == "postgres" or normalized_username.startswith("pg_"):
        raise InstallerError("Zabbix cannot use a PostgreSQL system role")


def validate_identifier(value: str, label: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise InstallerError(f"Invalid Zabbix database {label}: {value}")


def sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
