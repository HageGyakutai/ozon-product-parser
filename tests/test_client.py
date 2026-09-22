import json
import time
from types import SimpleNamespace

import pytest

from ozon_parser.client import fetch_product, product_session
from ozon_parser.session_data import save_browser_session


def test_cookie_domains_are_checked_at_label_boundary(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"domain": "fakeozon.ru", "name": "bad", "value": "bad"},
                {"domain": ".ozon.ru", "name": "good", "value": "ok"},
            ]
        ),
        encoding="utf-8",
    )
    session = product_session(str(path))
    try:
        assert [cookie.name for cookie in session.cookies] == ["good"]
    finally:
        session.close()


def test_antibot_html_is_not_treated_as_product():
    response = SimpleNamespace(
        status_code=200,
        url="https://www.ozon.ru/product/123/",
        text="<html><title>Antibot Challenge Page</title></html>",
        raise_for_status=lambda: None,
    )
    session = SimpleNamespace(get=lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="blocked automated HTTP access"):
        fetch_product(session, "123")


def test_browser_session_roundtrip_preserves_user_agent_and_cookie_attributes(tmp_path):
    path = tmp_path / "cookies.json"
    save_browser_session(
        path,
        [
            {
                "domain": ".ozon.ru",
                "path": "/product",
                "secure": True,
                "expires": int(time.time()) + 3600,
                "name": "session",
                "value": "secret",
            },
            {
                "domain": "www.ozon.ru",
                "path": "/",
                "secure": False,
                "expires": -1,
                "name": "session_cookie",
                "value": "other",
            },
        ],
        "Firefox browser UA",
    )
    assert path.stat().st_mode & 0o777 == 0o600
    session = product_session(str(path))
    try:
        assert session.headers["User-Agent"] == "Firefox browser UA"
        persistent = next(c for c in session.cookies if c.name == "session")
        assert persistent.domain == ".ozon.ru"
        assert persistent.path == "/product"
        assert persistent.secure is True
        assert persistent.expires > time.time()
        assert next(c for c in session.cookies if c.name == "session_cookie").expires is None
    finally:
        session.close()


def test_expired_and_foreign_cookies_are_ignored(tmp_path):
    path = tmp_path / "cookies.json"
    save_browser_session(
        path,
        [
            {"domain": "fakeozon.ru", "name": "foreign", "value": "a"},
            {"domain": "ozon.ru.evil.test", "name": "foreign2", "value": "b"},
            {
                "domain": ".ozon.ru",
                "name": "expired",
                "value": "c",
                "expires": int(time.time()) - 10,
            },
            {"domain": "www.ozon.ru", "name": "valid", "value": "d", "expires": -1},
        ],
        "Browser UA",
    )
    session = product_session(str(path))
    try:
        assert [c.name for c in session.cookies] == ["valid"]
    finally:
        session.close()


def test_all_expired_cookies_fail_without_revealing_values(tmp_path):
    path = tmp_path / "cookies.json"
    save_browser_session(
        path, [{"domain": "ozon.ru", "name": "secret", "value": "sensitive", "expires": 1}], "UA"
    )
    with pytest.raises(ValueError, match="No usable Ozon cookies") as exc:
        product_session(str(path))
    assert "sensitive" not in str(exc.value)


def test_session_rejects_invalid_metadata(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "user_agent": "bad\rheader",
                "cookies": [{"domain": "ozon.ru", "name": "a", "value": "b"}],
            }
        )
    )
    with pytest.raises(ValueError, match="Cookie file damaged"):
        product_session(str(path))


def test_403_antibot_does_not_claim_cookies_are_invalid():
    response = SimpleNamespace(
        status_code=403,
        url="https://www.ozon.ru/product/123/",
        text="<html><title>Antibot Challenge Page</title></html>",
        raise_for_status=lambda: None,
    )
    session = SimpleNamespace(get=lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="blocked automated HTTP access") as exc:
        fetch_product(session, "123")
    assert "may still be valid" in str(exc.value)


def test_plain_403_is_reported_as_http_client_forbidden():
    response = SimpleNamespace(
        status_code=403,
        url="https://www.ozon.ru/product/123/",
        text="<html><title>Forbidden</title></html>",
        raise_for_status=lambda: None,
    )
    session = SimpleNamespace(get=lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="HTTP 403") as exc:
        fetch_product(session, "123")
    assert "does not prove" in str(exc.value)


def test_401_reports_expired_or_unauthorized_session():
    response = SimpleNamespace(
        status_code=401,
        url="https://www.ozon.ru/product/123/",
        text="<html></html>",
        raise_for_status=lambda: None,
    )
    session = SimpleNamespace(get=lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="HTTP 401"):
        fetch_product(session, "123")
