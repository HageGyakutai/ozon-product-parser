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
    monkeypatch.setattr(cdp_browser, "_chrome_executable", lambda expected_path=None: "/usr/bin/chrome")
    monkeypatch.setenv("OZON_CHROME_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setattr(cdp_browser.time, "sleep", lambda seconds: None)

    def popen(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return SimpleNamespace(poll=lambda expected_path=None: None)

    monkeypatch.setattr(cdp_browser.subprocess, "Popen", popen)

    assert cdp_browser.ensure_cdp_browser(
        "http://127.0.0.1:9222", start_url="https://data.ozon.ru/"
    )
    assert "--remote-debugging-port=9222" in captured["command"]
    assert "--lang=ru-RU" in captured["command"]
    assert "https://data.ozon.ru/" in captured["command"]
    assert (tmp_path / "profile").is_dir()
    assert captured["start_new_session"] is True


def test_headless_chrome_flags(monkeypatch, tmp_path):
    states = iter([False, True])
    captured = {}
    monkeypatch.setattr(cdp_browser, "cdp_is_ready", lambda endpoint: next(states))
    monkeypatch.setattr(cdp_browser, "_chrome_executable", lambda expected_path=None: "/usr/bin/chromium")
    monkeypatch.setenv("OZON_CHROME_PROFILE", str(tmp_path / "profile"))
    monkeypatch.setenv("OZON_CHROME_HEADLESS", "true")
    monkeypatch.setattr(cdp_browser.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        cdp_browser.subprocess,
        "Popen",
        lambda command, **kwargs: captured.setdefault(
            "process", SimpleNamespace(command=command, poll=lambda expected_path=None: None)
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


def test_playwright_installation_waits_until_browser_appears(monkeypatch, tmp_path):
    executable = tmp_path / "chromium"
    executable.touch()
    results = iter([None, None, str(executable)])
    sleeps = []
    monkeypatch.setattr(cdp_browser.subprocess, "run", lambda command, **kwargs: None)
    monkeypatch.setattr(
        cdp_browser,
        "_playwright_chromium_executable",
        lambda expected_path=None: next(results),
    )
    monkeypatch.setattr(cdp_browser.time, "sleep", sleeps.append)

    assert cdp_browser._install_playwright_chromium() == str(executable)
    assert sleeps == [
        cdp_browser.PLAYWRIGHT_DISCOVERY_INTERVAL,
        cdp_browser.PLAYWRIGHT_DISCOVERY_INTERVAL,
    ]


def test_expected_playwright_executable_avoids_nested_playwright(monkeypatch, tmp_path):
    executable = tmp_path / "playwright-chromium"
    executable.touch()

    assert cdp_browser._playwright_chromium_executable(str(executable)) == str(executable)


def test_chrome_executable_uses_installed_playwright_browser(monkeypatch, tmp_path):
    executable = tmp_path / "playwright-chromium"
    executable.touch()
    monkeypatch.delenv("OZON_CHROME_EXECUTABLE", raising=False)
    monkeypatch.setattr(cdp_browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        cdp_browser,
        "_playwright_chromium_executable",
        lambda expected_path=None: str(executable),
    )

    assert cdp_browser._chrome_executable() == str(executable)


def test_chrome_executable_installs_playwright_browser(monkeypatch):
    monkeypatch.delenv("OZON_CHROME_EXECUTABLE", raising=False)
    monkeypatch.setattr(cdp_browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(cdp_browser, "_playwright_chromium_executable", lambda expected_path=None: None)
    monkeypatch.setattr(
        cdp_browser,
        "_install_playwright_chromium",
        lambda expected_path=None: "/cache/playwright/chromium",
    )

    assert cdp_browser._chrome_executable() == "/cache/playwright/chromium"


def test_playwright_installation_uses_current_python(monkeypatch, tmp_path):
    executable = tmp_path / "chromium"
    executable.touch()
    captured = {}
    monkeypatch.setattr(
        cdp_browser.subprocess,
        "run",
        lambda command, **kwargs: captured.update(command=command, **kwargs),
    )
    monkeypatch.setattr(
        cdp_browser,
        "_playwright_chromium_executable",
        lambda expected_path=None: str(executable),
    )

    assert cdp_browser._install_playwright_chromium() == str(executable)
    assert captured["command"] == [
        cdp_browser.sys.executable,
        "-m",
        "playwright",
        "install",
        "chromium",
    ]
    assert captured["check"] is True


@pytest.mark.parametrize("value", ["not-a-number", "-1", "31"])
def test_invalid_startup_delay_is_rejected(monkeypatch, value):
    monkeypatch.setenv("OZON_CHROME_STARTUP_DELAY", value)

    with pytest.raises(RuntimeError, match="OZON_CHROME_STARTUP_DELAY"):
        cdp_browser._startup_delay()


def test_default_profile_is_a_path():
    assert isinstance(cdp_browser.DEFAULT_PROFILE, Path)
