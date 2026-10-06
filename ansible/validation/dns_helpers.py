"""Minimal DNS client for querying independent public resolvers directly."""

import ipaddress
import secrets
import socket
import struct


TYPES = {"A": 1, "PTR": 12, "MX": 15, "TXT": 16}


def resolve(resolver, name, record_type):
    query_id = secrets.randbits(16)
    question = encode_name(name) + struct.pack("!HH", TYPES[record_type], 1)
    packet = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(5)
        client.sendto(packet, (resolver, 53))
        response, _ = client.recvfrom(65535)
    reply_id, flags, questions, answers, _, _ = struct.unpack("!HHHHHH", response[:12])
    if reply_id != query_id:
        raise RuntimeError(f"{resolver} returned a mismatched DNS reply for {name}")
    if flags & 0x0200:
        raise RuntimeError(f"{resolver} returned a truncated DNS reply for {name}")
    if flags & 0x000F not in (0, 3):
        raise RuntimeError(f"{resolver} failed {record_type} lookup for {name} with rcode {flags & 0x000F}")
    offset = 12
    for _ in range(questions):
        _, offset = read_name(response, offset)
        offset += 4
    records = []
    for _ in range(answers):
        _, offset = read_name(response, offset)
        answer_type, _, _, length = struct.unpack("!HHIH", response[offset:offset + 10])
        offset += 10
        data = response[offset:offset + length]
        if answer_type == TYPES[record_type]:
            records.append(decode_record(response, offset, data, record_type))
        offset += length
    return records


def reverse_name(address):
    return ipaddress.IPv4Address(address).reverse_pointer


def decode_record(response, offset, data, record_type):
    if record_type == "A":
        return socket.inet_ntoa(data)
    if record_type == "PTR":
        return read_name(response, offset)[0]
    if record_type == "MX":
        return read_name(response, offset + 2)[0]
    chunks, position = [], 0
    while position < len(data):
        size = data[position]
        chunks.append(data[position + 1:position + 1 + size].decode(errors="replace"))
        position += 1 + size
    return "".join(chunks)


def encode_name(name):
    return b"".join(bytes([len(label)]) + label.encode("idna") for label in name.rstrip(".").split(".")) + b"\0"


def read_name(message, offset):
    labels, jumped, end = [], False, offset
    for _ in range(128):
        size = message[offset]
        if size & 0xC0 == 0xC0:
            if not jumped:
                end = offset + 2
            offset = struct.unpack("!H", message[offset:offset + 2])[0] & 0x3FFF
            jumped = True
            continue
        if size == 0:
            return ".".join(labels).lower(), end if jumped else offset + 1
        labels.append(message[offset + 1:offset + 1 + size].decode("idna"))
        offset += 1 + size
    raise RuntimeError("DNS name compression loop")
