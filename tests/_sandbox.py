"""Sandbox-server plumbing shared by the browser suites.

Each sandbox binds OS-assigned free ports, and the readiness wait fails at
once if our own server died. (Hard-coded ports used to collide with other
services on the development host: a suite's own uvicorn failed to bind, the
open-port poll adopted the foreign service instead, and every
`window.geomagModelExplorer` readiness wait timed out.)
"""
from __future__ import annotations

import socket
import time


def free_ports(n: int) -> list[int]:
    """`n` distinct ports nothing listens on right now (the OS picks them;
    all held open together so the same one is never handed out twice)."""
    socks = [socket.socket() for _ in range(n)]
    try:
        for s in socks:
            s.bind(("127.0.0.1", 0))
        return [s.getsockname()[1] for s in socks]
    finally:
        for s in socks:
            s.close()


def wait_port(port, proc, timeout=30.0):
    """Wait until `proc` (the suite's own server) listens on `port`.

    Raises if `proc` exits first (e.g. the port was taken), so a foreign
    listener on the port is never mistaken for the sandbox."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"sandbox server for :{port} exited ({proc.returncode})")
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"server on :{port} never came up")
