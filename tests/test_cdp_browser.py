from pathlib import Path
from types import SimpleNamespace

import pytest

from ozon_parser import cdp_browser


def test_ensure_cdp_browser_reuses_ready_session(monkeypatch):
    monkeypatch.setattr(cdp_browser, "cdp_is_ready", lambda endpoint: True)
    monkeypatch.setattr(
        cdp_browser.subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("Chrome must not be started"),
    )

    assert (
        cdp_browser.ensure_cdp_browser("http://127.0.0.1:9222", start_url="https://data.ozon.ru/")
        is False
    )


def test_ensure_cdp_browser_starts_chrome_and_waits(monkeypatch, tmp_path):
    states = iter([False, False, True])
    captured = {}
    monkeypatch.setattr(cdp_browser, "cdp_is_ready", lambda endpoint: next(states))
    monkeypatch.setattr(cdp_browser, "_chrome_executable", lambda: "/usr/bin/chrome")
    monkeypatch.setenv("OZON_CHROME_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setattr(cdp_browser.time, "sleep", lambda seconds: None)

    def popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(poll=lambda: None)

    monkeypatch.setattr(cdp_browser.subprocess, "Popen", popen)

    assert cdp_browser.ensure_cdp_browser(
        "http://127.0.0.1:9222", start_url="https://data.ozon.ru/"
    )
    assert "--remote-debugging-port=9222" in captured["command"]
    assert "https://data.ozon.ru/" in captured["command"]
    assert (tmp_path / "profile").is_dir()
    assert captured["start_new_session"] is True


def test_headless_chrome_flags(monkeypatch, tmp_path):
    states = iter([False, True])
    captured = {}
    monkeypatch.setattr(cdp_browser, "cdp_is_ready", lambda endpoint: next(states))
    monkeypatch.setattr(cdp_browser, "_chrome_executable", lambda: "/usr/bin/chromium")
    monkeypatch.setenv("OZON_CHROME_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("OZON_CHROME_HEADLESS", "true")
    monkeypatch.setattr(cdp_browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        cdp_browser.subprocess,
        "Popen",
        lambda command, **kwargs: captured.setdefault(
            "process", SimpleNamespace(command=command, poll=lambda: None)
        ),
    )

    cdp_browser.ensure_cdp_browser("http://127.0.0.1:9222", start_url="https://www.ozon.ru/")

    command = captured["process"].command
    assert "--headless=new" in command
    assert "--no-sandbox" in command
    assert "--disable-dev-shm-usage" in command
    assert "--disable-quic" in command
    assert "--disable-features=UseDnsHttpsSvcbAlpn" in command


@pytest.mark.parametrize("value", ["maybe", "enabled"])
def test_invalid_headless_value_is_rejected(monkeypatch, value):
    monkeypatch.setenv("OZON_CHROME_HEADLESS", value)

    with pytest.raises(RuntimeError, match="OZON_CHROME_HEADLESS"):
        cdp_browser._headless_enabled()


def test_automatic_start_rejects_remote_endpoint(monkeypatch):
    monkeypatch.setattr(cdp_browser, "cdp_is_ready", lambda endpoint: False)

    with pytest.raises(RuntimeError, match="only a local"):
        cdp_browser.ensure_cdp_browser(
            "https://remote.example:9222", start_url="https://data.ozon.ru/"
        )


def test_configured_chrome_must_exist(monkeypatch, tmp_path):
    missing = tmp_path / "missing-chrome"
    monkeypatch.setenv("OZON_CHROME_EXECUTABLE", str(missing))

    with pytest.raises(RuntimeError, match="does not exist"):
        cdp_browser._chrome_executable()


@pytest.mark.parametrize("value", ["not-a-number", "-1", "31"])
def test_invalid_startup_delay_is_rejected(monkeypatch, value):
    monkeypatch.setenv("OZON_CHROME_STARTUP_DELAY", value)

    with pytest.raises(RuntimeError, match="OZON_CHROME_STARTUP_DELAY"):
        cdp_browser._startup_delay()


def test_default_profile_is_a_path():
    assert isinstance(cdp_browser.DEFAULT_PROFILE, Path)
