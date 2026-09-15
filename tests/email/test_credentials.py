"""Security-first tests for production email credential storage."""
from __future__ import annotations
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.email.credentials import CredentialStore, EmailCredentials, InMemoryCredentialStore, KeyringCredentialStore
SECRET_PASSWORD="super-secret-password-7f4c"; SECRET_ACCESS="access-secret-8a2d"; SECRET_REFRESH="refresh-secret-9b3e"

class TestCredentialStoreInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError): CredentialStore()  # type: ignore
    def test_requires_get_password(self):
        class Partial(CredentialStore): pass
        with pytest.raises(TypeError): Partial()
    def test_complete_implementation_is_instantiable(self):
        class Partial(CredentialStore):
            def get_password(self,service,username): return None
            def set_password(self,service,username,password): pass
            def delete_password(self,service,username): pass
            def get_token(self,service,token_type): return None
            def set_token(self,service,token_type,token,expires_at=None): pass
            def delete_token(self,service,token_type): pass
        assert Partial() is not None

class TestInMemoryCredentialStore:
    def test_round_trip_password(self):
        s=InMemoryCredentialStore(); s.set_password("smtp","u","secret123"); assert s.get_password("smtp","u")=="secret123"
    def test_round_trip_token_and_expiry(self):
        s=InMemoryCredentialStore(); s.set_token("oauth","access","token123",1000.0); assert s.get_token("oauth","access")=="token123"; assert s.get_token_expiry("oauth","access")==1000.0
    def test_delete_credentials(self):
        s=InMemoryCredentialStore(); s.set_password("s","u","p"); s.set_token("s","t","tok"); s.delete_password("s","u"); s.delete_token("s","t"); assert s.get_password("s","u") is None; assert s.get_token("s","t") is None

class TestKeyringCredentialStore:
    def test_round_trip_uses_backend_and_keeps_expiry_separately(self):
        class FakeKeyring:
            def __init__(self): self.values={}
            def get_password(self,service,username): return self.values.get((service,username))
            def set_password(self,service,username,password): self.values[(service,username)]=password
            def delete_password(self,service,username): self.values.pop((service,username),None)
        b=FakeKeyring(); s=KeyringCredentialStore(keyring_backend=b); s.set_password("mark.email","acct-1",SECRET_PASSWORD); s.set_token("mark.email/acct-1","access",SECRET_ACCESS,123.0); s.set_token("mark.email/acct-1","refresh",SECRET_REFRESH)
        assert s.get_password("mark.email","acct-1")==SECRET_PASSWORD; assert s.get_token("mark.email/acct-1","access")==SECRET_ACCESS; assert s.get_token_expiry("mark.email/acct-1","access")==123.0; assert s.get_token("mark.email/acct-1","refresh")==SECRET_REFRESH

class TestEmailCredentials:
    def test_rejects_secret_oauth_fields(self):
        with pytest.raises(ValueError):
            EmailCredentials.from_config("user@example.com","smtp.example.com",465,"imap.example.com",993,"email/user",{"client_id":"public","access_token":SECRET_ACCESS,"refresh_token":SECRET_REFRESH,"client_secret":SECRET_PASSWORD})
    def test_serialization_contains_only_allowlisted_oauth_metadata(self):
        c=EmailCredentials.from_config("user@example.com","smtp.example.com",465,"imap.example.com",993,oauth_config={"client_id":"public","token_uri":"https://oauth.example/token"}); out=json.dumps(c.to_dict()); assert "client_id" in out and "token_uri" in out; assert all(x not in out for x in (SECRET_ACCESS,SECRET_REFRESH,SECRET_PASSWORD,"access_token","refresh_token"))
    def test_no_secret_attributes(self):
        c=EmailCredentials("user@example.com","smtp.example.com",587,"imap.example.com",993); assert not hasattr(c,"password"); assert not hasattr(c,"secret"); assert not hasattr(c,"token")
