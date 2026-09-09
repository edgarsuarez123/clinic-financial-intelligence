from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings
from app.security import hash_password, token_hash

PASSWORD = "test-only-long-password"

class MemoryStore:
    """Test double only. Production uses PostgreSQL Store without fallback."""
    def __init__(self):
        self.user = {"user_id":uuid4(),"username":"owner", "password_hash":hash_password(PASSWORD)}
        self.sessions = {}
        self.events = []
        self.count = 0
        self.active = True
        self.audit_failure = False
    def check_runtime(self): pass
    def ready(self): pass
    def audit(self, *args):
        if self.audit_failure:
            raise RuntimeError("sensitive database connection details")
        self.events.append(args)
    def login_allowed(self, username):
        self.count += 1
        return self.count <= 5
    def find_user(self, username):
        return self.user if username == "owner" and self.active else None
    def create_session(self, uid, digest, expires_at, request_id):
        self.audit(uid,"auth.login","auth",request_id,"success")
        self.sessions[digest] = expires_at
        return True
    def resolve_session(self, digest):
        expiry = self.sessions.get(digest)
        return self.user if self.active and expiry and expiry > datetime.now(timezone.utc) else None
    def revoke_session(self, digest, actor, request_id):
        self.sessions.pop(digest,None)
        self.audit(actor,"auth.logout","auth",request_id,"success")

@pytest.fixture
def api():
    store = MemoryStore()
    with TestClient(create_app(Settings("postgresql://unused"),store)) as client:
        yield client,store

def login(client):
    response = client.post("/api/v1/auth/login",json={"username":"owner","password":PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return token,{"Authorization":"Bearer "+token}

@pytest.mark.parametrize("path",["auth/me","health","openapi.json"])
def test_anonymous_denied(api,path):
    client,store = api
    r = client.get("/api/v1/"+path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert store.events[-1][1] == "auth.denied"

def test_login_identity_and_logout(api):
    client,store = api
    token,headers = login(client)
    assert token not in store.sessions
    assert token_hash(token) in store.sessions
    r = client.get("/api/v1/auth/me",headers=headers)
    assert r.json() == {"user_id":str(store.user["user_id"]),"username":"owner"}
    assert r.headers["cache-control"] == "no-store"
    assert store.events[-1][1] == "account.read"
    assert client.post("/api/v1/auth/logout",headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me",headers=headers).status_code == 401

def test_expired_session(api):
    client,store = api
    token,headers = login(client)
    store.sessions[token_hash(token)] = datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.get("/api/v1/auth/me",headers=headers).status_code == 401

def test_deactivated_account_denied(api):
    client,store = api
    _,headers = login(client)
    store.active = False
    assert client.get("/api/v1/auth/me",headers=headers).status_code == 401

@pytest.mark.parametrize("header",["Bearer invalid", "Basic dXNlcjpwYXNz", "Bearer " + "a"*257])
def test_invalid_credentials(api,header):
    assert api[0].get("/api/v1/auth/me",headers={"Authorization":header}).status_code == 401

def test_no_account_enumeration(api):
    client,_ = api
    statuses=[]
    for user in ("owner","unknown"):
        r=client.post("/api/v1/auth/login",json={"username":user,"password":"wrong"})
        statuses.append((r.status_code,r.json()["error"]["message"]))
    assert statuses[0] == statuses[1]

def test_throttled_login(api):
    client,_ = api
    for _ in range(5):
        assert client.post("/api/v1/auth/login",json={"username":"owner","password":"wrong"}).status_code == 401
    r=client.post("/api/v1/auth/login",json={"username":"owner","password":PASSWORD})
    assert r.status_code == 429
    assert "Retry-After" in r.headers

def test_validation_does_not_echo_secrets(api):
    client,_ = api
    r=client.post("/api/v1/auth/login",json={"username":"owner","password":"secret"*100})
    assert r.status_code == 422
    assert "secret" not in r.text
    assert r.json()["error"]["request_id"] == r.headers["X-Request-ID"]

def test_audit_failure_is_fail_closed(api):
    client,store = api
    _,headers=login(client)
    store.audit_failure=True
    r=client.get("/api/v1/auth/me",headers=headers)
    assert r.status_code == 500
    assert "sensitive" not in r.text
    assert "owner" not in r.text

def test_unmatched_paths_and_docs_hidden(api):
    client,_=api
    for path in ("/docs","/openapi.json","/api/v1/transactions"):
        r=client.get(path)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "http_404"

def test_authenticated_health_and_schema(api):
    client,_=api
    _,headers=login(client)
    assert client.get("/api/v1/health",headers=headers).json()["status"] == "ok"
    schema=client.get("/api/v1/openapi.json",headers=headers).json()
    assert "/api/v1/auth/login" in schema["paths"]
