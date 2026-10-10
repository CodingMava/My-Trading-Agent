import socket

import pytest
import requests
from curl_cffi import requests as curl_requests

from tests.conftest import NetworkBlocked


def test_the_suite_cannot_reach_the_network():
    with pytest.raises(NetworkBlocked):
        requests.get("https://api.telegram.org", timeout=5)  # Telegram, Kite: plain requests
    with pytest.raises(NetworkBlocked):
        curl_requests.Session().get("https://query1.finance.yahoo.com")  # how yfinance fetches
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 443), timeout=5)
