"""The browser suites' sandbox plumbing (tests/_sandbox.py): free ports are
really free and distinct, and a sandbox server that dies is reported at
once instead of the wait running out."""
from __future__ import annotations

import socket
import subprocess
import sys

import pytest
from _sandbox import free_ports, wait_port


def test_free_ports_are_distinct_and_bindable():
    ports = free_ports(3)
    assert len(set(ports)) == 3
    for port in ports:
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))


def test_wait_port_returns_once_the_server_listens():
    (port,) = free_ports(1)
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port),
                             "--bind", "127.0.0.1"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_port(port, proc)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_wait_port_fails_fast_when_the_server_dies():
    (port,) = free_ports(1)
    proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    with pytest.raises(RuntimeError, match=r"exited \(3\)"):
        wait_port(port, proc, timeout=10.0)
