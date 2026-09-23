"""Tests for the experimental requests-only Ozon login."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock


def load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "get_cookies_requests.py"
    spec = importlib.util.spec_from_file_location("get_cookies_requests_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


login = load_script()


PHONE_HTML = """
<form action="/phone" method="post">
  <input type="hidden" name="csrf" value="token">
  <input type="tel" name="phone" autocomplete="tel">
</form>
"""

CODE_HTML = """
<form action="/verify" method="post">
  <input type="hidden" name="csrf" value="next-token">
  <input type="text" name="verificationCode" autocomplete="one-time-code">
</form>
"""


def test_find_login_form_recognizes_phone_input():
    form, field = login.find_login_form(PHONE_HTML, login.PHONE_MARKERS)

    assert form["action"] == "/phone"
    assert field["name"] == "phone"


def test_find_login_form_recognizes_verification_code():
    form, field = login.find_login_form(CODE_HTML, login.CODE_MARKERS)

    assert form["action"] == "/verify"
    assert field["name"] == "verificationCode"


def test_submit_login_form_preserves_hidden_fields():
    response = Mock()
    response.text = PHONE_HTML
    response.url = "https://sso.ozon.ru/login"
    submitted = Mock()
    submitted.raise_for_status.return_value = None
    session = Mock()
    session.post.return_value = submitted

    result = login.submit_login_form(
        session,
        response,
        markers=login.PHONE_MARKERS,
        value="9230000000",
    )

    assert result is submitted
    session.post.assert_called_once_with(
        "https://sso.ozon.ru/phone",
        data={"csrf": "token", "phone": "9230000000"},
        timeout=30,
        allow_redirects=True,
    )


def test_missing_html_form_explains_javascript_limitation():
    try:
        login.find_login_form("<html><div id='app'></div></html>", login.PHONE_MARKERS)
    except RuntimeError as exc:
        assert "requires JavaScript" in str(exc)
    else:
        raise AssertionError("missing login form must fail")
