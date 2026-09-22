import importlib.util
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "check_gmail", Path(__file__).resolve().parents[1] / "scripts" / "check_gmail.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def fake_service():
    return SimpleNamespace(
        users=lambda: SimpleNamespace(
            getProfile=lambda **kwargs: SimpleNamespace(execute=lambda: {"emailAddress": "hidden"})
        )
    )


def test_oauth_check_does_not_display_email(monkeypatch, caplog):
    monkeypatch.setattr(check, "gmail_service", lambda *args: fake_service())
    monkeypatch.setattr(sys, "argv", ["check_gmail.py"])
    with caplog.at_level(logging.INFO):
        assert check.main() == 0
    assert "Gmail API access confirmed" in caplog.text
    assert "hidden" not in caplog.text


def test_wait_for_code_does_not_display_value(monkeypatch, caplog):
    monkeypatch.setattr(check, "gmail_service", lambda *args: fake_service())
    seen = []

    def wait(service, since, timeout):
        seen.append((since, timeout))
        return "123456"

    monkeypatch.setattr(check, "wait_for_code", wait)
    monkeypatch.setattr(sys, "argv", ["check_gmail.py", "--wait-for-code", "--timeout", "10"])
    with caplog.at_level(logging.INFO):
        assert check.main() == 0
    assert seen[0][0].tzinfo is not None and seen[0][1] == 10
    assert "code found" in caplog.text
    assert "123456" not in caplog.text


@pytest.mark.parametrize(
    "exception", [FileNotFoundError("credentials missing"), TimeoutError("expired")]
)
def test_credentials_missing_or_code_timeout_returns_failure(monkeypatch, exception):
    if isinstance(exception, FileNotFoundError):
        monkeypatch.setattr(check, "gmail_service", lambda *args: (_ for _ in ()).throw(exception))
        monkeypatch.setattr(sys, "argv", ["check_gmail.py"])
    else:
        monkeypatch.setattr(check, "gmail_service", lambda *args: fake_service())
        monkeypatch.setattr(
            check, "wait_for_code", lambda *args, **kwargs: (_ for _ in ()).throw(exception)
        )
        monkeypatch.setattr(sys, "argv", ["check_gmail.py", "--wait-for-code"])
    assert check.main() == 1
