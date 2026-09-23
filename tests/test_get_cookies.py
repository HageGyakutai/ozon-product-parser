"""Regression tests for the Playwright login page lifecycle."""

from unittest.mock import Mock

from scripts.get_cookies import login_page


def test_login_page_creates_initial_tab_for_fresh_context():
    page = Mock()
    context = Mock()
    context.pages = []
    context.new_page.return_value = page

    assert login_page(context) is page
    context.new_page.assert_called_once_with()


def test_login_page_reuses_existing_open_tab():
    page = Mock()
    page.is_closed.return_value = False
    context = Mock()
    context.pages = [page]

    assert login_page(context) is page
    context.new_page.assert_not_called()
