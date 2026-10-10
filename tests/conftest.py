"""No test may use the network (the audit's Level 1 criterion): fakes stand in for every provider. This
blocks Python sockets and DNS lookups beyond this machine, and curl_cffi, the HTTP library yfinance uses."""
import socket

import pytest

LOCAL = {"localhost", "127.0.0.1", "::1", None}


class NetworkBlocked(RuntimeError):
    pass


def _local_only(original):
    def guarded(self, address, *args, **kwargs):
        if isinstance(address, tuple) and address[0] not in LOCAL:
            raise NetworkBlocked(f"tests must not use the network (tried {address[0]})")
        return original(self, address, *args, **kwargs)
    return guarded


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    lookup = socket.getaddrinfo

    def local_lookup(host, *args, **kwargs):
        if host not in LOCAL:
            raise NetworkBlocked(f"tests must not use the network (looked up {host})")
        return lookup(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_lookup)
    monkeypatch.setattr(socket.socket, "connect", _local_only(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _local_only(socket.socket.connect_ex))
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return

    def blocked(*args, **kwargs):
        raise NetworkBlocked("tests must not use the network (curl_cffi)")

    monkeypatch.setattr(curl_requests.Session, "request", blocked)
