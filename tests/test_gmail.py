import base64
import json
import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

import pytest

from ozon_parser.gmail import gmail_service, verification_code, wait_for_code


def part(text, mime="text/plain"):
    data = base64.urlsafe_b64encode(text.encode()).decode()
    return {"mimeType": mime, "body": {"data": data}}


def message(sender, parts, received=2000):
    return {"internalDate": str(received), "payload": {
        "headers": [{"name": "From", "value": sender}], "parts": parts,
    }}


class FakeService:
    def __init__(self, data):
        self.data = data
        self.queries = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kwargs):
        self.queries.append(kwargs)
        return SimpleNamespace(execute=lambda: {"messages": [{"id": k} for k in self.data]})

    def get(self, **kwargs):
        return SimpleNamespace(execute=lambda: self.data[kwargs["id"]])


@pytest.mark.parametrize("body", ["Ваш код: 123456", "123456 — код для входа", "Code 123456"])
def test_code_formats(body):
    assert verification_code(body) == "123456"
    assert verification_code("No verification here") is None


@pytest.mark.parametrize("parts", [
    [part("Ваш код: 123456")],
    [part("<p>Ваш <strong>код</strong>: 123456</p>", "text/html")],
    [{"mimeType": "multipart/mixed", "parts": [part("Code 123456")]}],
])
def test_wait_for_code_reads_plain_html_and_nested_mime(parts):
    service = FakeService({"new": message("Ozon <login@mail.ozon.ru>", parts)})
    assert wait_for_code(service, datetime.fromtimestamp(1, UTC), query="subject:login") == "123456"
    assert service.queries[0]["q"] == "after:1 subject:login"


def test_old_spoofed_and_codeless_messages_are_skipped():
    service = FakeService({
        "old": message("login@ozon.ru", [part("Code 111111")], received=999),
        "spoofed": message("Ozon <login@fakeozon.ru>", [part("Code 222222")]),
        "other": message("Ozon <login@ozon.ru.evil.test>", [part("Code 333333")]),
        "empty": message("login@ozon.ru", [part("No verification here")]),
        "valid": message("login@ozon.ru", [part("444444 — код для входа")]),
    })
    assert wait_for_code(service, datetime.fromtimestamp(1, UTC)) == "444444"


def test_timeout_without_matching_email(monkeypatch):
    clock = iter([0, 0, 0, 1, 1, 1, 2, 2])
    monkeypatch.setattr("ozon_parser.gmail.time", SimpleNamespace(
        monotonic=lambda: next(clock), sleep=lambda _: None,
    ))
    service = FakeService({"old": message("login@ozon.ru", [part("Code 123456")], received=0)})
    with pytest.raises(TimeoutError, match="No new Ozon verification"):
        wait_for_code(service, datetime.fromtimestamp(1, UTC), timeout=2, interval=1)


def test_sender_domain_is_configurable(monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER_DOMAINS", "notifications.example.org")
    service = FakeService({
        "new": message("sender@notifications.example.org", [part("Code 123456")]),
    })
    assert wait_for_code(service, datetime.fromtimestamp(1, UTC)) == "123456"


def test_expired_oauth_token_is_refreshed_without_new_login(tmp_path, monkeypatch):
    credentials_file = tmp_path / "credentials.json"
    credentials_file.write_text("{}")
    token_file = tmp_path / "token.json"
    token_file.write_text("old")
    events = []

    class FakeCredentials:
        valid = False
        expired = True
        refresh_token = "available"

        @classmethod
        def from_authorized_user_file(cls, path, scopes):
            events.append("loaded")
            return cls()

        def refresh(self, request):
            events.append("refreshed")

        def to_json(self):
            return json.dumps({"refreshed": True})

    def module(name, **attributes):
        obj = ModuleType(name)
        obj.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, obj)

    module("google.auth.transport.requests", Request=object)
    module("google.oauth2.credentials", Credentials=FakeCredentials)
    module("google_auth_oauthlib.flow", InstalledAppFlow=SimpleNamespace(
        from_client_secrets_file=lambda *args: pytest.fail("Unexpected new OAuth login")
    ))
    module("googleapiclient.discovery", build=lambda *args, **kwargs: "gmail-service")
    assert gmail_service(str(credentials_file), str(token_file)) == "gmail-service"
    assert events == ["loaded", "refreshed"]
    assert json.loads(token_file.read_text()) == {"refreshed": True}
