"""Experimental Ozon login performed only through requests.Session."""

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests
from dotenv import load_dotenv

from ozon_parser.gmail import gmail_service, wait_for_code
from ozon_parser.session_data import ozon_cookie_domain, save_browser_session

LOGGER = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
NAVIGATION_HEADERS = {
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}
PHONE_MARKERS = ("phone", "tel", "mobile")
CODE_MARKERS = ("code", "otp", "verification", "one-time")


def _input_marker(field: Any) -> str:
    return " ".join(
        str(field.get(attribute, ""))
        for attribute in ("name", "id", "type", "autocomplete", "placeholder")
    ).casefold()


def find_login_form(html: str, markers: tuple[str, ...]) -> tuple[Any, Any]:
    """Return the form and named input matching phone or verification-code markers."""
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        for field in form.find_all("input"):
            name = field.get("name")
            marker = _input_marker(field)
            if isinstance(name, str) and name and any(item in marker for item in markers):
                return form, field
    raise RuntimeError(
        "Ozon login form was not found in HTML. The current Ozon ID page probably "
        "requires JavaScript, so pure requests authentication is unavailable."
    )


def submit_login_form(
    session: requests.Session,
    response: requests.Response,
    *,
    markers: tuple[str, ...],
    value: str,
) -> requests.Response:
    """Submit one HTML login form while preserving its hidden fields and cookies."""
    form, target_field = find_login_form(response.text, markers)
    payload: dict[str, str] = {}
    for field in form.find_all("input"):
        name = field.get("name")
        field_value = field.get("value", "")
        if isinstance(name, str) and name and isinstance(field_value, str):
            payload[name] = field_value
    payload[str(target_field["name"])] = value

    action = form.get("action") or response.url
    url = urljoin(response.url, str(action))
    method = str(form.get("method", "post")).casefold()
    if method == "get":
        result = session.get(url, params=payload, timeout=30, allow_redirects=True)
    else:
        result = session.post(url, data=payload, timeout=30, allow_redirects=True)
    result.raise_for_status()
    return result


def requests_session() -> requests.Session:
    """Create the isolated HTTP session used by the experimental login."""
    return requests.Session(impersonate="chrome", headers=NAVIGATION_HEADERS)


def portable_cookies(session: requests.Session) -> list[dict[str, object]]:
    """Convert requests cookies into the format consumed by parse_ozon.py."""
    result: list[dict[str, object]] = []
    for cookie in session.cookies.jar:
        if not ozon_cookie_domain(cookie.domain):
            continue
        result.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path or "/",
                "expires": cookie.expires if cookie.expires is not None else -1,
                "secure": cookie.secure,
            }
        )
    return result


def authenticate(session: requests.Session, phone: str, gmail: Any) -> None:
    """Open Ozon ID, submit the phone and then submit the fresh Gmail code."""
    LOGGER.info("Opening data.ozon.ru through requests")
    response = session.get("https://data.ozon.ru/", timeout=30, allow_redirects=True)
    response.raise_for_status()
    LOGGER.info("Submitting phone through requests")
    started = datetime.now(UTC)
    response = submit_login_form(session, response, markers=PHONE_MARKERS, value=phone)

    LOGGER.info("Waiting for new Gmail verification email")
    code = wait_for_code(gmail, started)
    LOGGER.info("Submitting Gmail verification code through requests")
    submit_login_form(session, response, markers=CODE_MARKERS, value=code)

    check = session.get("https://data.ozon.ru/", timeout=30, allow_redirects=True)
    check.raise_for_status()
    if "sso.ozon.ru" in check.url:
        raise RuntimeError("Ozon requests login did not complete; session is still on Ozon ID")


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    phone = os.getenv("OZON_PHONE", "").strip()
    if not re.fullmatch(r"\+?[0-9]{10,15}", phone):
        raise ValueError("OZON_PHONE must contain 10–15 digits with optional leading +")

    gmail = gmail_service(
        os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"),
        os.getenv("GMAIL_TOKEN_FILE", "token.json"),
    )
    with requests_session() as session:
        authenticate(session, phone, gmail)
        cookies = portable_cookies(session)
        if not cookies:
            raise RuntimeError("Ozon requests login returned no Ozon cookies")
        path = Path(os.getenv("OZON_COOKIES_FILE", "cookies.json"))
        save_browser_session(path, cookies, USER_AGENT)
    LOGGER.info("Ozon requests login completed; cookies saved to %s", path)


if __name__ == "__main__":
    main()
