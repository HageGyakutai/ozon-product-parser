import json
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.cookies import create_cookie
from urllib3.util.retry import Retry

from .auth_guard import blocked_page_text
from .session_data import ozon_cookie_domain


def product_session(cookies_file: str = "cookies.json") -> requests.Session:
    path = Path(cookies_file)
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; authenticate first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == 1:
            cookies = data.get("cookies")
            user_agent = data.get("user_agent")
            if (
                not isinstance(user_agent, str)
                or not user_agent.strip()
                or "\n" in user_agent
                or "\r" in user_agent
            ):
                raise ValueError("Invalid browser User-Agent")
        elif isinstance(data, list):
            # Legacy cookie files did not record the browser User-Agent.
            cookies, user_agent = data, None
        else:
            raise ValueError("Invalid session format")
        if not isinstance(cookies, list):
            raise ValueError("Expected a list of cookies")
    except (ValueError, OSError) as exc:
        raise ValueError("Cookie file damaged; authenticate again") from exc
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    if user_agent is not None:
        session.headers["User-Agent"] = user_agent
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        ),
    )
    now = time.time()
    for cookie in cookies:
        if not isinstance(cookie, dict) or not ozon_cookie_domain(cookie.get("domain")):
            continue
        name, value = cookie.get("name"), cookie.get("value")
        domain, cookie_path = cookie["domain"], cookie.get("path", "/")
        expiry, secure = cookie.get("expires"), cookie.get("secure", False)
        if not isinstance(name, str) or not name or not isinstance(value, str):
            continue
        if not isinstance(cookie_path, str) or not cookie_path.startswith("/"):
            continue
        if type(secure) is not bool:
            continue
        if expiry is not None:
            if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
                continue
            # Playwright uses -1 for session cookies.
            if expiry > 0 and expiry <= now:
                continue
            if expiry <= 0:
                expiry = None
            else:
                expiry = int(expiry)
        session.cookies.set_cookie(
            create_cookie(
                name=name,
                value=value,
                domain=domain,
                path=cookie_path,
                secure=secure,
                expires=expiry,
            )
        )
    if not session.cookies:
        raise ValueError("No usable Ozon cookies; authenticate again")
    return session


def fetch_product(session: requests.Session, sku: str) -> str:
    response = session.get(f"https://www.ozon.ru/product/{sku}/", timeout=20)
    blocked = (
        "antibot challenge" in response.text[:10000].casefold()
        or blocked_page_text(response.text)
    )
    if blocked:
        raise ValueError(
            f"Ozon blocked automated HTTP access to SKU={sku} "
            f"(HTTP {response.status_code}); browser cookies may still be valid"
        )
    if response.status_code == 401:
        raise ValueError(
            f"Ozon returned HTTP 401 for SKU={sku}; "
            "the saved session is not authorized or has expired"
        )
    if response.status_code == 403:
        raise ValueError(
            f"Ozon returned HTTP 403 for SKU={sku}; access is forbidden for this HTTP client. "
            "This does not prove that the browser cookies are invalid"
        )
    if response.status_code == 404:
        raise ValueError(f"SKU={sku} not found")
    response.raise_for_status()
    if "data.ozon.ru" in response.url or "sso.ozon.ru" in response.url:
        raise ValueError("Ozon redirected to login; saved session is not authorized")
    return response.text
