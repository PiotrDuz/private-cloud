#!/usr/bin/env python3
"""Match AmneziaWG's UDP tunnel compatibility wrappers to installed headers."""

import re
import sys
from pathlib import Path


def main():
    compat_path = Path(sys.argv[1])
    header_path = Path(sys.argv[2])
    compat = compat_path.read_text()
    header = header_path.read_text()

    setup_arg = function_pointer_type(header, "setup_udp_tunnel_sock", has_net=True, header_path=header_path)
    release_arg = function_pointer_type(header, "udp_tunnel_sock_release", has_net=False, header_path=header_path)
    compat = set_wrapper(compat, "setup_udp_tunnel_sock", setup_arg)
    compat = set_wrapper(compat, "udp_tunnel_sock_release", release_arg)

    old = compat_path.read_text()
    if compat != old:
        compat_path.write_text(compat)
        print("updated")
    else:
        print("unchanged")


def function_pointer_type(header, function_name, has_net, header_path):
    if has_net:
        pattern = rf"\b{re.escape(function_name)}\s*\(\s*struct\s+net\s*\*\s*\w+\s*,\s*struct\s+(sock|socket)\s*\*"
    else:
        pattern = rf"\b{re.escape(function_name)}\s*\(\s*struct\s+(sock|socket)\s*\*"
    match = re.search(pattern, header, re.S)
    if not match:
        raise RuntimeError(f"Could not determine the {function_name} argument type from {header_path}")
    return match.group(1)


def set_wrapper(compat, function_name, header_arg_type):
    wrapper = (
        rf"^#define {re.escape(function_name)}\(net, sk, sock_cfg\) .*$"
        if function_name == "setup_udp_tunnel_sock"
        else rf"^#define {re.escape(function_name)}\(sk\) .*$"
    )
    matches = list(re.finditer(wrapper, compat, re.M))
    if len(matches) > 1 or (header_arg_type == "socket" and not matches):
        raise RuntimeError(f"Expected one {function_name} compatibility wrapper for the socket API; found {len(matches)}")
    if header_arg_type == "sock":
        if not matches:
            return compat
        return re.sub(wrapper + r"\n?", "", compat, count=1, flags=re.M)
    return compat


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Expected the compatibility header and kernel udp_tunnel.h paths")
    main()
