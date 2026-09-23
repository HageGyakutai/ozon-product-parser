import importlib.util
import json
import sys
from pathlib import Path

import pytest

from ozon_parser.extractor import extract_product

spec = importlib.util.spec_from_file_location(
    "parse_ozon", Path(__file__).resolve().parents[1] / "scripts" / "parse_ozon.py"
)
parse_ozon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parse_ozon)


def fixture_html():
    state = {
        "@type": "Product",
        "sku": "123",
        "name": "Offline product",
        "offers": {"price": "12.50"},
    }
    return '<script type="application/ld+json">' + json.dumps(state) + "</script>"


def test_offline_parses_same_extractor_without_network_or_cookie_file(tmp_path, monkeypatch):
    path = tmp_path / "captured.html"
    path.write_text(fixture_html(), encoding="utf-8")
    saved = []

    class FakeEngine:
        def dispose(self):
            pass

    class FakeDb:
        def __init__(self, engine):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(parse_ozon, "database_engine", FakeEngine)
    monkeypatch.setattr(parse_ozon, "prepare_database", lambda *args, **kwargs: None)
    monkeypatch.setattr(parse_ozon, "Session", FakeDb)
    monkeypatch.setattr(parse_ozon, "save_product", lambda db, product: saved.append(product))
    monkeypatch.setattr(parse_ozon, "product_session", lambda *args: pytest.fail("cookies opened"))
    monkeypatch.setattr(parse_ozon, "fetch_product", lambda *args: pytest.fail("network used"))
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123", "--html-file", str(path)])
    parse_ozon.main()
    assert saved == [extract_product(fixture_html(), "123")]


def test_offline_rejects_multiple_skus(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123", "456", "--html-file", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        parse_ozon.main()
    assert exc.value.code == 2


def test_debug_html_redacts_common_secrets_and_preserves_product(tmp_path):
    from ozon_parser.debug_html import save_debug_html

    state = {
        "@type": "Product",
        "sku": "123",
        "name": "Item",
        "user": {"email": "person@example.org", "phone": "+7 999 111 22 33"},
        "widget": json.dumps({"sessionToken": "very-secret-value"}),
    }
    html = (
        '<form><input value="password"></form><script type="application/json">'
        + json.dumps(state)
        + '</script><script>alert("private")</script>'
    )
    path = tmp_path / "debug.html"
    save_debug_html(path, html)
    snapshot = path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
    for secret in (
        "person@example.org",
        "+7 999 111 22 33",
        "very-secret-value",
        "password",
        'alert("private")',
    ):
        assert secret not in snapshot
    assert extract_product(snapshot, "123").title == "Item"
