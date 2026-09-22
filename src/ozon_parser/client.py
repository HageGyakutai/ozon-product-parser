import json
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def product_session(cookies_file: str = "cookies.json") -> requests.Session:
    path = Path(cookies_file)
    if not path.is_file():
        raise FileNotFoundError(f"{path} missing; authenticate first")
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cookies, list):
            raise ValueError("Expected a list of cookies")
    except (ValueError, OSError) as exc:
        raise ValueError("Cookie file damaged; authenticate again") from exc
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
    )
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        ),
    )
    for cookie in cookies:
        if (
            cookie.get("domain", "").endswith("ozon.ru")
            and cookie.get("name")
            and cookie.get("value")
        ):
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie["domain"],
                path=cookie.get("path", "/"),
            )
    if not session.cookies:
        raise ValueError("No usable Ozon cookies; authenticate again")
    return session


def fetch_product(session: requests.Session, sku: str) -> str:
    response = session.get(f"https://www.ozon.ru/product/{sku}/", timeout=20)
    if response.status_code in (401, 403):
        raise ValueError(f"Ozon rejected cookies for SKU={sku}; authenticate again")
    if response.status_code == 404:
        raise ValueError(f"SKU={sku} not found")
    response.raise_for_status()
    if "data.ozon.ru" in response.url:
        raise ValueError("Ozon redirected to login; authenticate again")
    return response.text
