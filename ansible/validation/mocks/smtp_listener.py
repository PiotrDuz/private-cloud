"""Serve implicit-TLS and plaintext SMTP clients on one trial port."""

import asyncio
import socket
import ssl

SNIFF_TIMEOUT = 1.5
TLS_HANDSHAKE_BYTE = 0x16


async def serve_sniffed(host, port, tls, handle_session):
    loop = asyncio.get_running_loop()
    listener = socket.create_server((host, port), backlog=64)
    listener.setblocking(False)
    sessions = set()
    while True:
        connection, _ = await loop.sock_accept(listener)
        session = asyncio.create_task(classify_and_serve(connection, tls, handle_session))
        sessions.add(session)
        session.add_done_callback(sessions.discard)


async def classify_and_serve(connection, tls, handle_session):
    loop = asyncio.get_running_loop()
    try:
        first = await loop.run_in_executor(None, peek_first_byte, connection)
        if first == b"":
            connection.close()
            return
        encrypted = first is not None and first[0] == TLS_HANDSHAKE_BYTE
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.connect_accepted_socket(lambda: protocol, connection, ssl=tls if encrypted else None)
        writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        await handle_session(reader, writer, encrypted)
    except (OSError, ssl.SSLError):
        connection.close()


def peek_first_byte(connection):
    connection.settimeout(SNIFF_TIMEOUT)
    try:
        return connection.recv(1, socket.MSG_PEEK)
    except TimeoutError:
        return None
    finally:
        connection.setblocking(False)
