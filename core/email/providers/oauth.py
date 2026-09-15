"""Internal OAuth provider adapter primitives."""
from __future__ import annotations
import asyncio, inspect, time, uuid
from typing import Any, Optional
from ..credentials import CredentialStore
from ..errors import AuthenticationError, AuthorizationError, ConnectionError, MailboxNotFoundError, MessageNotFoundError, ProviderCapabilityError, RateLimitError, TimeoutError, TransientProviderError, PermanentProviderError
from ..models import EmailAccount, EmailAddress, EmailAttachment, EmailDraft, EmailFolder, EmailMessage, EmailMessageRef, EmailOperationResult, EmailSearchQuery, EmailThread, OperationStatus
from .base import Capability, EmailProvider, ProviderCapabilities, ProviderConnectionState, ProviderMetadata

class OAuthProviderBase(EmailProvider):
    provider_type="oauth"; capabilities:tuple[Capability,...]=(); credential_service_prefix="mark-liii.email"
    def __init__(self, client:Any=None): self._client=client; self._state=ProviderConnectionState.DISCONNECTED; self._account:Optional[EmailAccount]=None; self._credentials:Optional[CredentialStore]=None; self._capabilities=ProviderCapabilities(self.capabilities)
    @property
    def metadata(self): return ProviderMetadata(self.provider_type,self._account.account_id if self._account else "",self._capabilities,self._state,self._account.display_name if self._account else "")
    @property
    def is_connected(self): return self._state in (ProviderConnectionState.CONNECTED,ProviderConnectionState.AUTHENTICATED)
    def _service(self): return f"{self.credential_service_prefix}/{self.provider_type}/{self._account.account_id}"
    def _config(self): return dict(getattr(self._account,"oauth_config",{}) or {})
    def _require(self,capability):
        if not self.supports(capability): raise ProviderCapabilityError(f"Provider does not support {capability.name}")
        if not self.is_connected: raise ConnectionError("Provider is not connected")
    async def _call(self,method,*args,**kwargs):
        if self._client is None: raise ConnectionError(f"{self.provider_type} client is not configured")
        fn=getattr(self._client,method,None)
        if fn is None: raise ProviderCapabilityError(f"Provider adapter does not implement {method}")
        try:
            result=fn(*args,**kwargs); return await result if inspect.isawaitable(result) else result
        except (AuthenticationError,AuthorizationError,ConnectionError,MailboxNotFoundError,MessageNotFoundError,ProviderCapabilityError,RateLimitError,TimeoutError,TransientProviderError,PermanentProviderError): raise
        except Exception as exc:
            status=getattr(exc,"status_code",None)
            if status==401: raise AuthenticationError(f"{self.provider_type} authentication failed") from exc
            if status==403: raise AuthorizationError(f"{self.provider_type} authorization failed") from exc
            if status==404: raise MessageNotFoundError(f"{self.provider_type} resource not found") from exc
            if status==429: raise RateLimitError(f"{self.provider_type} rate limit exceeded",retry_after=getattr(exc,"retry_after",None)) from exc
            if status and status>=500: raise TransientProviderError(f"{self.provider_type} service temporarily unavailable") from exc
            raise ConnectionError(f"{self.provider_type} request failed") from exc
    @staticmethod
    def _result(ref=None,metadata=None): return EmailOperationResult(str(uuid.uuid4()),OperationStatus.SUCCESS,[ref] if ref else [],metadata or {})
    @staticmethod
    def _address(v): return v if isinstance(v,EmailAddress) else EmailAddress(v.get("address","") if isinstance(v,dict) else str(v or ""),v.get("name","") if isinstance(v,dict) else "")
    def _ref(self,v,mailbox="INBOX"):
        if isinstance(v,EmailMessageRef):
            if v.account_id!=self._account.account_id: raise AuthorizationError("Message reference belongs to another account")
            return v
        native=str(v.get("id") if isinstance(v,dict) else v); return EmailMessageRef(self._account.account_id,mailbox,native,native)
    async def connect(self,account,credentials,timeout=None):
        if timeout is not None and timeout<=0: raise ValueError("timeout must be positive")
        self._state=ProviderConnectionState.CONNECTING; self._account=account; self._credentials=credentials
        try:
            access=credentials.get_token(self._service(),"access"); refresh=credentials.get_token(self._service(),"refresh"); expiry=credentials.get_token_expiry(self._service(),"access"); config=self._config()
            if not access and not refresh: raise AuthenticationError("No OAuth credentials found")
            if not access or (expiry is not None and expiry<=time.time()+30):
                if not refresh: raise AuthenticationError("OAuth access token is missing or expired")
                refreshed=await self._call("refresh",refresh,config); access=refreshed.get("access_token") if isinstance(refreshed,dict) else refreshed
                if not access: raise AuthenticationError("OAuth refresh did not return an access token")
                credentials.set_token(self._service(),"access",access,expires_at=refreshed.get("expires_at") if isinstance(refreshed,dict) else None)
            await self._call("authenticate",access,refresh,config); self._state=ProviderConnectionState.AUTHENTICATED; return self.metadata
        except asyncio.CancelledError:
            self._state=ProviderConnectionState.DISCONNECTED; self._account=None; self._credentials=None; raise
        except Exception:
            self._state=ProviderConnectionState.DISCONNECTED; self._account=None; self._credentials=None; raise
    async def disconnect(self):
        if self._state==ProviderConnectionState.DISCONNECTED:return
        self._state=ProviderConnectionState.DISCONNECTING
        try:
            if self._client is not None and hasattr(self._client,"close"):
                r=self._client.close();
                if inspect.isawaitable(r): await r
        finally: self._state=ProviderConnectionState.DISCONNECTED; self._account=None; self._credentials=None
    def _folder(self,v):
        if isinstance(v,EmailFolder): return v
        return EmailFolder(str(v.get("id",v.get("name",""))),str(v.get("name","")),bool(v.get("selectable",True)),bool(v.get("read_only",False)),v.get("special_use"))
    async def list_folders(self): self._require(Capability.FOLDERS); return [self._folder(v) for v in await self._call("list_folders")]
    async def get_folder_info(self,name): self._require(Capability.FOLDERS); return self._folder(await self._call("get_folder",name))
    async def select_folder(self,name): self._require(Capability.FOLDERS); return self._folder(await self._call("select_folder",name))
    async def search(self,q): self._require(Capability.SEARCH); return [self._ref(v,v.get("mailbox","INBOX") if isinstance(v,dict) else "INBOX") for v in await self._call("search",q)]
    def _validate_ref(self,r):
        if r.account_id!=self._account.account_id: raise AuthorizationError("Message reference belongs to another account")
    def _message(self,v,r):
        if isinstance(v,EmailMessage): return v
        return EmailMessage(r,self._address(v.get("sender","")),[self._address(x) for x in v.get("recipients",[])],subject=v.get("subject",""),date=v.get("date"),flags=list(v.get("flags",[])),body_plain=v.get("body_plain"),body_html=v.get("body_html"),attachments=[self._attachment(x) for x in v.get("attachments",[])],thread_id=v.get("thread_id"),provider_metadata=dict(v.get("provider_metadata",{})))
    def _attachment(self,v):
        if isinstance(v,EmailAttachment): return v
        return EmailAttachment(str(v.get("id","")),v.get("filename",""),v.get("content_type","application/octet-stream"),int(v.get("byte_size",0)),v.get("disposition","attachment"),v.get("content_id"),v.get("content_handle"))
    async def fetch_message(self,r,include_body=True,include_attachments=False): self._require(Capability.FETCH); self._validate_ref(r); return self._message(await self._call("get_message",r,include_body=include_body,include_attachments=include_attachments),r)
    async def fetch_message_headers(self,r): return await self.fetch_message(r,False,False)
    async def fetch_attachments(self,r): self._require(Capability.ATTACHMENTS); self._validate_ref(r); return [self._attachment(v) for v in await self._call("get_attachments",r)]
    async def mark_read(self,r): self._require(Capability.READ_STATE); self._validate_ref(r); await self._call("mark_read",r); return self._result(r)
    async def mark_unread(self,r): self._require(Capability.READ_STATE); self._validate_ref(r); await self._call("mark_unread",r); return self._result(r)
    async def add_flag(self,r,f): self._require(Capability.FLAGS); self._validate_ref(r); await self._call("add_flag",r,f); return self._result(r)
    async def remove_flag(self,r,f): self._require(Capability.FLAGS); self._validate_ref(r); await self._call("remove_flag",r,f); return self._result(r)
    async def delete_message(self,r): self._require(Capability.DELETE); self._validate_ref(r); await self._call("delete",r); return self._result(r)
    async def move_message(self,r,f): self._require(Capability.MOVE); self._validate_ref(r); await self._call("move",r,f); return self._result(r)
    async def copy_message(self,r,f): self._require(Capability.COPY); self._validate_ref(r); await self._call("copy",r,f); return self._result(r)
    async def archive_message(self,r): self._require(Capability.ARCHIVE); self._validate_ref(r); await self._call("archive",r); return self._result(r)
    async def search_threads(self,q): self._require(Capability.THREADS); return [v if isinstance(v,EmailThread) else EmailThread(v["thread_key"],[self._ref(x) for x in v.get("messages",[])],v.get("subject",""),v.get("first_message_date"),v.get("last_message_date")) for v in await self._call("search_threads",q)]
    async def get_thread(self,k): self._require(Capability.THREADS); v=await self._call("get_thread",k); return v if isinstance(v,EmailThread) else EmailThread(v["thread_key"],[self._ref(x) for x in v.get("messages",[])],v.get("subject",""))
    async def create_draft(self,d): self._require(Capability.DRAFTS); v=await self._call("create_draft",d); return self._result(v if isinstance(v,EmailMessageRef) else None,{"draft_id":v.get("draft_id")} if isinstance(v,dict) else {})
    async def update_draft(self,r,d): self._require(Capability.DRAFTS); self._validate_ref(r); await self._call("update_draft",r,d); return self._result(r)
    async def delete_draft(self,r): self._require(Capability.DRAFTS); self._validate_ref(r); await self._call("delete_draft",r); return self._result(r)
    async def send(self,account,to,subject,body_plain=None,body_html=None,attachments=None,cc=None,bcc=None,reply_to=None):
        self._require(Capability.SEND)
        if account.account_id!=self._account.account_id: raise AuthorizationError("Send account does not match connected account")
        await self._call("send",account,to,subject,body_plain,body_html,attachments,cc,bcc,reply_to); return self._result()
    def supports(self,capability): return self._capabilities.supports(capability)
