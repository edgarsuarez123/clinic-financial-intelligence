import io
import json
import logging
import pytest
from app.security import hash_password, verify_password, token_hash
from app.settings import Settings
from app.logging_config import JsonFormatter

def test_password_hashing_and_verification():
    password="some-long-test-password"
    first=hash_password(password)
    assert first.startswith("$argon2id$")
    assert hash_password(password) != first
    assert verify_password(first,password)
    assert not verify_password(first,"incorrect")
    assert not verify_password("malformed",password)

@pytest.mark.parametrize("value",["short","a"*257])
def test_password_policy(value):
    with pytest.raises(ValueError): hash_password(value)

def test_token_digest():
    assert len(token_hash("test")) == 64
    assert token_hash("test") == token_hash("test")
    assert token_hash("test") != token_hash("other")

@pytest.mark.parametrize("kwargs",[
 {"database_url":"sqlite:///test.db"},
 {"database_url":"postgresql://test","session_minutes":0},
 {"database_url":"postgresql://test","login_limit":0},
 {"database_url":"postgresql://test","log_level":"arbitrary"},
])
def test_configuration_fails_closed(kwargs):
    with pytest.raises(ValueError): Settings(**kwargs)

def test_log_formatter_excludes_arbitrary_fields():
    record=logging.LogRecord("clinic",logging.ERROR,"",1,"password=private",(),None)
    record.event="request.failed"
    record.request_id="id"
    record.password="private"
    result=JsonFormatter().format(record)
    assert "private" not in result
    assert json.loads(result)["event"] == "request.failed"
