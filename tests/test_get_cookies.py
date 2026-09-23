"""Regression tests for the Playwright login page lifecycle."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def load_login_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "get_cookies.py"
    spec = importlib.util.spec_from_file_location("get_cookies_page_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


login = load_login_script()


def test_login_page_creates_initial_tab_for_fresh_context():
    page = Mock()
    context = Mock()
    context.pages = []
    context.new_page.return_value = page

    assert login.login_page(context) is page
    context.new_page.assert_called_once_with()


def test_login_page_reuses_existing_open_tab():
    page = Mock()
    page.is_closed.return_value = False
    context = Mock()
    context.pages = [page]

    assert login.login_page(context) is page
    context.new_page.assert_not_called()
