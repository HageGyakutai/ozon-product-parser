"""Probe Ozon with a browser-like requests.Session without changing parser behavior."""

import argparse
import logging
from pathlib import Path

import requests

from ozon_parser.auth_guard import blocked_page_text
from ozon_parser.client import product_session

LOGGER = logging.getLogger(__name__)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


def browser_like_session(user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    """Create an anonymous session with navigation headers similar to Chrome."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    session.headers["User-Agent"] = user_agent
    return session


def prepare_authenticated_session(cookies_file: Path) -> requests.Session:
    """Load browser cookies and complement their recorded User-Agent with navigation headers."""
    session = product_session(str(cookies_file))
    session.headers.update(BROWSER_HEADERS)
    return session


def probe(session: requests.Session, url: str, *, label: str) -> requests.Response | None:
    """Request one page and log a secret-free diagnostic summary."""
    try:
        response = session.get(url, timeout=30, allow_redirects=True)
    except requests.RequestException as exc:
        LOGGER.error("%s request failed: %s", label, exc)
        return None

    blocked = (
        response.status_code in {401, 403, 429}
        or "antibot challenge" in response.text[:10000].casefold()
        or blocked_page_text(response.text)
    )
    LOGGER.info(
        "%s status=%s blocked=%s bytes=%s final_url=%s cookies_in_session=%s",
        label,
        response.status_code,
        blocked,
        len(response.content),
        response.url,
        len(session.cookies),
    )
    return response


def run_probe(session: requests.Session, sku: str, *, mode: str) -> bool:
    """Warm up the session on Ozon and then request the product page."""
    probe(session, "https://www.ozon.ru/", label=f"{mode}:home")
    product = probe(
        session,
        f"https://www.ozon.ru/product/{sku}/",
        label=f"{mode}:product",
    )
    return (
        product is not None
        and product.status_code == 200
        and not (
            "antibot challenge" in product.text[:10000].casefold()
            or blocked_page_text(product.text)
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare anonymous and cookie-backed requests.Session access to Ozon"
    )
    parser.add_argument("sku", help="Ozon product SKU")
    parser.add_argument(
        "--cookies",
        type=Path,
        default=Path("cookies.json"),
        help="browser session file created by get_cookies.py",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with browser_like_session() as anonymous:
        anonymous_ok = run_probe(anonymous, args.sku, mode="anonymous")

    authenticated_ok = False
    if args.cookies.is_file():
        try:
            with prepare_authenticated_session(args.cookies) as authenticated:
                authenticated_ok = run_probe(authenticated, args.sku, mode="cookies")
        except (OSError, ValueError) as exc:
            LOGGER.error("Cannot load %s: %s", args.cookies, exc)
    else:
        LOGGER.warning("%s not found; cookie-backed probe skipped", args.cookies)

    if authenticated_ok:
        LOGGER.info("RESULT requests works with saved browser cookies")
        return 0
    if anonymous_ok:
        LOGGER.info("RESULT anonymous requests works for this product")
        return 0
    LOGGER.warning("RESULT Ozon refused requests; keep using browser transport")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
