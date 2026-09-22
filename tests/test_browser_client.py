import time

from ozon_parser.browser_client import _playwright_cookies


def test_playwright_cookies_preserve_browser_metadata():
    expires = int(time.time()) + 3600
    cookies = _playwright_cookies(
        [
            {
                "name": "sid",
                "value": "secret",
                "domain": ".ozon.ru",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "no_restriction",
                "expires": expires,
            }
        ]
    )

    assert cookies == [
        {
            "name": "sid",
            "value": "secret",
            "domain": ".ozon.ru",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "sameSite": "None",
            "expires": float(expires),
        }
    ]


def test_playwright_cookies_ignore_expired_and_foreign_entries():
    cookies = _playwright_cookies(
        [
            {
                "name": "expired",
                "value": "x",
                "domain": ".ozon.ru",
                "expires": int(time.time()) - 5,
            },
            {
                "name": "foreign",
                "value": "x",
                "domain": "example.org",
                "expires": -1,
            },
            {
                "name": "session",
                "value": "ok",
                "domain": "www.ozon.ru",
                "expires": -1,
            },
        ]
    )

    assert [cookie["name"] for cookie in cookies] == ["session"]
