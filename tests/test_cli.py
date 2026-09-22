import csv
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ozon_parser.client import product_session
from ozon_parser.models import Product


def script(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parse = script("parse_ozon")
login = script("get_cookies")


class ContextManager:
    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeBrowser:
    def __init__(self):
        self.closed = False
        self.context = SimpleNamespace(
            pages=[SimpleNamespace(evaluate=lambda _: "Test Browser UA", is_closed=lambda: False)],
            cookies=lambda: [{"domain": "ozon.ru", "name": "sid", "value": "test"}],
        )

    def new_context(self, **kwargs):
        return self.context

    def close(self):
        self.closed = True


def setup_login(monkeypatch, tmp_path):
    browser = FakeBrowser()
    playwright = SimpleNamespace(
        chromium=SimpleNamespace(launch=lambda **kwargs: browser),
        firefox=SimpleNamespace(launch=lambda **kwargs: browser),
        webkit=SimpleNamespace(launch=lambda **kwargs: browser),
    )

    # A class instance provides a context manager without launching Playwright.
    class FakePlaywright:
        def __enter__(self):
            return playwright

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(login, "sync_playwright", FakePlaywright)
    monkeypatch.setattr(login, "gmail_service", lambda *args: object())
    monkeypatch.setenv("OZON_PHONE", "79991112233")
    monkeypatch.setenv("OZON_COOKIES_FILE", str(tmp_path / "cookies.json"))
    monkeypatch.delenv("OZON_BROWSER", raising=False)
    monkeypatch.delenv("OZON_BROWSER_CHANNEL", raising=False)
    return browser, tmp_path / "cookies.json"


@pytest.mark.parametrize(
    ("phone", "error"),
    [
        (None, "Set OZON_PHONE"),
        ("abc123", "OZON_PHONE must"),
    ],
)
def test_login_rejects_missing_or_invalid_phone(monkeypatch, phone, error):
    if phone is None:
        monkeypatch.delenv("OZON_PHONE", raising=False)
    else:
        monkeypatch.setenv("OZON_PHONE", phone)
    monkeypatch.setattr(login, "gmail_service", lambda *args: pytest.fail("Gmail opened"))
    with pytest.raises(ValueError, match=error):
        login.main()


@pytest.mark.parametrize(
    ("browser", "channel", "error"),
    [
        ("safari", "", "OZON_BROWSER must"),
        ("chromium", "unsupported", "OZON_BROWSER_CHANNEL must"),
        ("firefox", "chrome", "available only"),
        ("webkit", "msedge", "available only"),
    ],
)
def test_login_rejects_invalid_browser_options(monkeypatch, tmp_path, browser, channel, error):
    setup_login(monkeypatch, tmp_path)
    monkeypatch.setenv("OZON_BROWSER", browser)
    monkeypatch.setenv("OZON_BROWSER_CHANNEL", channel)
    with pytest.raises(ValueError, match=error):
        login.main()


@pytest.mark.parametrize(
    "failure",
    [
        "Antibot Challenge Page",
        "Verification was not completed",
    ],
)
def test_login_never_saves_cookies_when_authentication_fails(
    monkeypatch,
    tmp_path,
    failure,
):
    browser, path = setup_login(monkeypatch, tmp_path)
    monkeypatch.setattr(
        login, "authenticate", lambda *args: (_ for _ in ()).throw(RuntimeError(failure))
    )
    with pytest.raises(RuntimeError, match=failure):
        login.main()
    assert not path.exists()
    assert browser.closed


def test_login_saves_cookies_only_after_authenticate_returns(monkeypatch, tmp_path):
    browser, path = setup_login(monkeypatch, tmp_path)
    monkeypatch.setattr(login, "authenticate", lambda *args: None)
    login.main()
    assert browser.closed
    assert path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    assert data["user_agent"] == "Test Browser UA"
    assert [cookie.name for cookie in product_session(str(path)).cookies] == ["sid"]


def test_antibot_page_aborts_login_without_saving_cookies(monkeypatch, tmp_path):
    browser, path = setup_login(monkeypatch, tmp_path)
    browser.context.pages[0].title = lambda: "Antibot Challenge Page"
    browser.context.pages[0].locator = lambda _: SimpleNamespace(inner_text=lambda: "Blocked")
    monkeypatch.setattr(
        login, "authenticate", lambda context, *args: login.ensure_not_blocked(context)
    )
    with pytest.raises(RuntimeError, match="No cookies saved"):
        login.main()
    assert not path.exists()


def setup_parse(monkeypatch):
    saved = []
    client = ContextManager()
    monkeypatch.setattr(parse, "product_session", lambda *args: client)
    monkeypatch.setattr(parse, "fetch_product", lambda session, sku: f"HTML for {sku}")
    monkeypatch.setattr(parse, "extract_product", lambda html, sku: Product(sku, f"Item {sku}"))
    monkeypatch.setattr(parse, "save_product", lambda db, product: saved.append(product))
    monkeypatch.setattr(parse, "Session", lambda engine: ContextManager())
    monkeypatch.setattr(parse, "database_engine", lambda: SimpleNamespace(dispose=lambda: None))
    return saved


@pytest.mark.parametrize("sku", ["abc", "١٢٣"])
def test_parser_invalid_sku_has_exit_2(monkeypatch, sku):
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", sku])
    with pytest.raises(SystemExit) as exc:
        parse.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("content", [None, "broken JSON"])
def test_parser_missing_or_damaged_cookie_file_has_exit_2(monkeypatch, tmp_path, content):
    path = tmp_path / "cookies.json"
    if content is not None:
        path.write_text(content)
    monkeypatch.setenv("OZON_COOKIES_FILE", str(path))
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123"])
    with pytest.raises(SystemExit) as exc:
        parse.main()
    assert exc.value.code == 2


def test_parser_missing_database_url_has_exit_2(monkeypatch):
    setup_parse(monkeypatch)
    monkeypatch.setattr(
        parse, "database_engine", lambda: (_ for _ in ()).throw(ValueError("DATABASE_URL missing"))
    )
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123"])
    with pytest.raises(SystemExit) as exc:
        parse.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("skus", [["123"], ["123", "456"]])
def test_parser_success_exit_0_and_nested_csv(monkeypatch, tmp_path, skus):
    saved = setup_parse(monkeypatch)
    csv_path = tmp_path / "nested" / "products.csv"
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", *skus, "--csv", str(csv_path)])
    assert parse.main() is None
    assert [product.sku for product in saved] == skus
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert [row["sku"] for row in csv.DictReader(stream)] == skus


def test_parser_partial_failure_exit_1_and_csv_only_contains_success(monkeypatch, tmp_path):
    saved = setup_parse(monkeypatch)
    monkeypatch.setattr(
        parse,
        "fetch_product",
        lambda client, sku: (
            "good" if sku == "456" else (_ for _ in ()).throw(ValueError("Page unavailable"))
        ),
    )
    csv_path = tmp_path / "products.csv"
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123", "456", "--csv", str(csv_path)])
    with pytest.raises(SystemExit) as exc:
        parse.main()
    assert exc.value.code == 1
    assert [product.sku for product in saved] == ["456"]
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        assert [row["sku"] for row in csv.DictReader(stream)] == ["456"]


def test_parser_browser_transport_uses_browser_client(monkeypatch):
    saved = []
    browser_client = ContextManager()
    browser_client.fetch_product = lambda sku: f"HTML for {sku}"

    monkeypatch.setattr(parse, "BrowserProductClient", lambda *args, **kwargs: browser_client)
    monkeypatch.setattr(
        parse,
        "fetch_product",
        lambda *args, **kwargs: pytest.fail("requests transport used"),
    )
    monkeypatch.setattr(parse, "extract_product", lambda html, sku: Product(sku, f"Item {sku}"))
    monkeypatch.setattr(parse, "save_product", lambda db, product: saved.append(product))
    monkeypatch.setattr(parse, "Session", lambda engine: ContextManager())
    monkeypatch.setattr(parse, "database_engine", lambda: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123", "--transport", "browser"])

    assert parse.main() is None
    assert [product.sku for product in saved] == ["123"]


def test_parser_browser_transport_passes_cdp_endpoint(monkeypatch):
    captured = {}
    browser_client = ContextManager()
    browser_client.fetch_product = lambda sku: f"HTML for {sku}"

    def make_browser_client(*args, **kwargs):
        captured.update(kwargs)
        return browser_client

    monkeypatch.setattr(parse, "BrowserProductClient", make_browser_client)
    monkeypatch.setattr(parse, "extract_product", lambda html, sku: Product(sku, f"Item {sku}"))
    monkeypatch.setattr(parse, "save_product", lambda db, product: None)
    monkeypatch.setattr(parse, "Session", lambda engine: ContextManager())
    monkeypatch.setattr(parse, "database_engine", lambda: SimpleNamespace(dispose=lambda: None))
    monkeypatch.setenv("OZON_CDP_ENDPOINT", "http://127.0.0.1:9222")
    monkeypatch.setattr(sys, "argv", ["parse_ozon.py", "123", "--transport", "browser"])

    assert parse.main() is None
    assert captured["cdp_endpoint"] == "http://127.0.0.1:9222"
