import io
import urllib.error
from unittest.mock import Mock
import pytest
from scripts.smoke_check import wait_for_status


class Response:
    def __init__(self, status): self.status = status
    def __enter__(self): return self
    def __exit__(self, *_): pass


def test_retries_connection_reset_then_requires_auth():
    opener = Mock(side_effect=[ConnectionResetError(), urllib.error.HTTPError('http://local',401,'Unauthorized',{},io.BytesIO())])
    sleep = Mock()
    wait_for_status('http://local',401,opener=opener,sleep=sleep)
    assert opener.call_count == 2
    sleep.assert_called_once_with(1)


def test_transient_gateway_error_then_web_ready():
    wait_for_status('http://local',200,opener=Mock(side_effect=[Response(503),Response(200)]),sleep=Mock())


def test_does_not_accept_anonymous_success_for_protected_api():
    with pytest.raises(RuntimeError,match='received HTTP 200'):
        wait_for_status('http://local',401,opener=Mock(return_value=Response(200)),sleep=Mock())


def test_persistent_failure_is_bounded():
    opener = Mock(side_effect=ConnectionResetError())
    with pytest.raises(RuntimeError,match='3 attempts'):
        wait_for_status('http://local',200,attempts=3,opener=opener,sleep=Mock())
    assert opener.call_count == 3
