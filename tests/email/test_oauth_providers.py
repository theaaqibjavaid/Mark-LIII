from __future__ import annotations
import pytest
from core.email.credentials import InMemoryCredentialStore
from core.email.models import EmailAccount, EmailAddress, EmailMessageRef, EmailSearchQuery
from core.email.providers.base import Capability, EmailProvider
from core.email.providers.gmail import GmailProvider
from core.email.providers.microsoft import MicrosoftProvider

class Adapter:
    def __init__(self): self.calls=[]
    def authenticate(self, access, refresh, config): self.calls.append(("authenticate",access)); return True
    def refresh(self, refresh, config): self.calls.append(("refresh",refresh)); return {"access_token":"new-access","expires_at":9999999999}
    def close(self): self.calls.append(("close",))
    def list_folders(self): return [{"id":"INBOX","name":"Inbox","special_use":"inbox"}]
    def get_folder(self, name): return {"id":name,"name":name}
    def select_folder(self, name): return {"id":name,"name":name}
    def search(self, query): return [{"id":"m1","mailbox":"INBOX"}]
    def get_message(self, ref, include_body=True, include_attachments=False): return {"sender":"sender@example.com","recipients":["user@example.com"],"subject":"Hello","body_plain":"body","flags":[],"thread_id":"provider-thread"}
    def get_attachments(self, ref): return []
    def mark_read(self, ref): pass
    def mark_unread(self, ref): pass
    def add_flag(self, ref, flag): pass
    def remove_flag(self, ref, flag): pass
    def delete(self, ref): pass
    def move(self, ref, folder): pass
    def copy(self, ref, folder): pass
    def archive(self, ref): pass
    def search_threads(self, query): return [{"thread_key":"native-thread","messages":[{"id":"m1"}],"subject":"Hello"}]
    def get_thread(self, key): return {"thread_key":key,"messages":[{"id":"m1"}],"subject":"Hello"}
    def create_draft(self, draft): return {"draft_id":"d1"}
    def update_draft(self, ref, draft): pass
    def delete_draft(self, ref): pass
    def send(self, *args): pass

@pytest.fixture(params=[GmailProvider, MicrosoftProvider])
def provider(request): return request.param(Adapter())

def account(provider_name):
    return EmailAccount("acct-1", provider_name, primary_address=EmailAddress("user@example.com"), oauth_config={"client_id":"public"})

def connected(provider, name):
    import asyncio
    store=InMemoryCredentialStore(); store.set_token(f"mark-liii.email/{name}/acct-1","access","access")
    asyncio.run(provider.connect(account(name),store)); return store

def test_provider_implements_contract(provider):
    assert isinstance(provider, EmailProvider)
    assert provider.supports(Capability.SEARCH)
    assert provider.supports(Capability.SEND)

def test_oauth_authentication_and_search(provider):
    import asyncio
    name=provider.provider_type; store=connected(provider,name)
    refs=asyncio.run(provider.search(EmailSearchQuery(subject="Hello")))
    assert refs[0].account_id=="acct-1" and refs[0].uid=="m1"

def test_provider_never_accepts_cross_account_reference(provider):
    import asyncio
    connected(provider,provider.provider_type)
    with pytest.raises(Exception):
        asyncio.run(provider.fetch_message(EmailMessageRef("other","INBOX","m1")))

def test_expired_access_token_refreshes_without_returning_secret(provider):
    import asyncio, time
    name=provider.provider_type; store=InMemoryCredentialStore(); svc=f"mark-liii.email/{name}/acct-1"
    store.set_token(svc,"access","expired",expires_at=time.time()-10); store.set_token(svc,"refresh","refresh-secret")
    asyncio.run(provider.connect(account(name),store))
    assert store.get_token(svc,"access")=="new-access"
    assert provider.metadata.account_id=="acct-1"
