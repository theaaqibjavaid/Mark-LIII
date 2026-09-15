from core.email.models import EmailAccount
from core.email.providers.gmail import GmailProvider
from core.email.providers.microsoft import MicrosoftProvider
from core.email.providers.registry import EmailProviderRegistry
from core.email.errors import ProviderCapabilityError

class EmptyAdapter: pass

def test_registry_selects_only_explicit_provider_type():
    registry=EmailProviderRegistry({"gmail":lambda:GmailProvider(EmptyAdapter()),"microsoft":lambda:MicrosoftProvider(EmptyAdapter())})
    assert isinstance(registry.discover(EmailAccount("a","gmail")),GmailProvider)
    assert isinstance(registry.discover(EmailAccount("b","microsoft")),MicrosoftProvider)

def test_registry_rejects_unknown_provider_instead_of_guessing():
    registry=EmailProviderRegistry({"gmail":lambda:GmailProvider(EmptyAdapter())})
    try: registry.discover(EmailAccount("a","imap"))
    except ProviderCapabilityError: return
    raise AssertionError("unknown provider must fail closed")

def test_registry_rejects_duplicate_provider_registration():
    registry=EmailProviderRegistry()
    registry.register("gmail",lambda:GmailProvider(EmptyAdapter()))
    try: registry.register("gmail",lambda:GmailProvider(EmptyAdapter()))
    except ValueError: return
    raise AssertionError("duplicate provider registration must fail")
