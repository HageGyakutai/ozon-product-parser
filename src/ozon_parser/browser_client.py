"""Browser transport for product pages using the saved Ozon session."""

import time
from pathlib import Path
from typing import Literal

from playwright._impl._api_structures import SetCookieParam
from playwright.sync_api import Browser, BrowserContext, Playwright, sync_playwright

from .auth_guard import blocked_page_text
from .cdp_browser import ensure_cdp_browser
from .session_data import load_browser_session, ozon_cookie_domain


def _playwright_cookies(cookies: list[dict]) -> list[SetCookieParam]:
    now = time.time()
    result: list[SetCookieParam] = []
    same_site_map: dict[str, Literal["Strict", "Lax", "None"]] = {
        "strict": "Strict",
        "lax": "Lax",
        "none": "None",
        "no_restriction": "None",
    }
    for item in cookies:
        if not isinstance(item, dict) or not ozon_cookie_domain(item.get("domain")):
            continue
        name, value = item.get("name"), item.get("value")
        domain = item.get("domain")
        path = item.get("path", "/")
        secure = item.get("secure", False)
        expires = item.get("expires")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value, str)
            or not isinstance(domain, str)
        ):
            continue
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        if type(secure) is not bool:
            continue
        cookie: SetCookieParam = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": secure,
        }
        if isinstance(expires, (int, float)) and not isinstance(expires, bool):
            if expires > 0 and expires <= now:
                continue
            if expires > 0:
                cookie["expires"] = float(expires)
        if type(item.get("httpOnly")) is bool:
            cookie["httpOnly"] = item["httpOnly"]
        same_site = item.get("sameSite")
        if isinstance(same_site, str):
            normalized = same_site_map.get(same_site.casefold())
            if normalized:
                cookie["sameSite"] = normalized
        result.append(cookie)
    return result


class BrowserProductClient:
    """Load authenticated product pages through Playwright and shared Chrome."""

    def __init__(
        self,
        cookies_file: str,
        browser_name: str = "chromium",
        channel: str | None = None,
        headless: bool = False,
        cdp_endpoint: str | None = None,
    ) -> None:
        path = Path(cookies_file)
        cookies, user_agent = load_browser_session(path)
        browser_name = browser_name.strip().lower()
        channel = channel.strip() if channel else None
        cdp_endpoint = cdp_endpoint.strip() if cdp_endpoint else None
        if browser_name not in {"chromium", "firefox", "webkit"}:
            raise ValueError("OZON_BROWSER must be chromium, firefox or webkit")
        if channel and channel not in {"chrome", "msedge"}:
            raise ValueError("OZON_BROWSER_CHANNEL must be chrome or msedge")
        if channel and browser_name != "chromium":
            raise ValueError("OZON_BROWSER_CHANNEL is available only with OZON_BROWSER=chromium")
        if cdp_endpoint and browser_name != "chromium":
            raise ValueError("OZON_CDP_ENDPOINT requires OZON_BROWSER=chromium")
        browser_cookies = _playwright_cookies(cookies)
        if not browser_cookies:
            raise ValueError("No usable Ozon cookies for browser transport")

        playwright = sync_playwright().start()
        self._playwright: Playwright | None = playwright
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._owns_browser = False
        self._owns_context = False
        try:
            if cdp_endpoint:
                ensure_cdp_browser(cdp_endpoint, start_url="https://www.ozon.ru/")
                self._browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
                if not self._browser.contexts:
                    raise RuntimeError("Connected Chrome has no default browser context")
                self._context = self._browser.contexts[0]
            else:
                launcher = getattr(playwright, browser_name)
                launch_options: dict[str, object] = {"headless": headless}
                if channel:
                    launch_options["channel"] = channel
                self._browser = launcher.launch(**launch_options)
                self._owns_browser = True
                if user_agent:
                    self._context = self._browser.new_context(
                        locale="ru-RU", user_agent=user_agent
                    )
                else:
                    self._context = self._browser.new_context(locale="ru-RU")
                self._owns_context = True
            assert self._context is not None
            self._context.add_cookies(browser_cookies)
        except Exception as exc:
            self.close()
            raise RuntimeError(f"Cannot start browser transport: {exc}") from exc

    def fetch_product(self, sku: str) -> str:
        assert self._context is not None
        page = self._context.new_page()
        try:
            response = page.goto(
                f"https://www.ozon.ru/product/{sku}/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            if response is None:
                raise ValueError(f"Browser did not receive an HTTP response for SKU={sku}")
            html = page.content()
            url = page.url
            if "data.ozon.ru" in url or "sso.ozon.ru" in url:
                raise ValueError("Ozon redirected browser transport to login")
            blocked = "antibot challenge" in html[:10000].casefold() or blocked_page_text(
                page.locator("body").inner_text()
            )
            if blocked:
                raise ValueError(
                    f"Ozon blocked browser transport for SKU={sku} "
                    f"(HTTP {response.status}); product HTML unavailable"
                )
            if response.status == 401:
                raise ValueError(
                    f"Ozon returned HTTP 401 in browser transport for SKU={sku}; "
                    "the saved session is not authorized or has expired"
                )
            if response.status == 403:
                raise ValueError(
                    f"Ozon returned HTTP 403 in browser transport for SKU={sku}; "
                    "the browser session was refused"
                )
            if response.status == 404:
                raise ValueError(f"SKU={sku} not found")
            if response.status >= 400:
                raise ValueError(
                    f"Ozon returned HTTP {response.status} in browser transport for SKU={sku}"
                )
            return html
        finally:
            page.close()

    def close(self) -> None:
        if self._context is not None:
            if self._owns_context:
                self._context.close()
            self._context = None
            self._owns_context = False
        if self._browser is not None:
            if self._owns_browser:
                self._browser.close()
            self._browser = None
            self._owns_browser = False
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
