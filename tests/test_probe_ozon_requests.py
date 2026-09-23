"""Tests for the isolated requests.Session probe."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def load_probe_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "probe_ozon_requests.py"
    spec = importlib.util.spec_from_file_location("probe_ozon_requests_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe_script = load_probe_script()


def response(status: int = 200, text: str = "<html>product</html>"):
    result = Mock()
    result.status_code = status
    result.text = text
    result.content = text.encode()
    result.url = "https://www.ozon.ru/product/123/"
    return result


def test_browser_like_session_has_navigation_headers():
    with probe_script.browser_like_session("test-agent") as session:
        assert session.headers["User-Agent"] == "test-agent"
        assert session.headers["Accept-Language"].startswith("ru-RU")
        assert session.headers["Upgrade-Insecure-Requests"] == "1"


def test_run_probe_warms_home_before_product():
    session = Mock()
    session.cookies = []
    session.get.side_effect = [response(), response()]

    assert probe_script.run_probe(session, "123", mode="anonymous") is True
    assert [call.args[0] for call in session.get.call_args_list] == [
        "https://www.ozon.ru/",
        "https://www.ozon.ru/product/123/",
    ]


def test_run_probe_reports_forbidden_product_as_failure():
    session = Mock()
    session.cookies = []
    session.get.side_effect = [response(), response(status=403, text="forbidden")]

    assert probe_script.run_probe(session, "123", mode="cookies") is False
