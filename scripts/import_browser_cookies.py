"""Convert a local browser JSON cookie export into the parser's session format."""

import argparse
import json
import tempfile
from pathlib import Path

from ozon_parser.client import product_session
from ozon_parser.session_data import ozon_cookie_domain, save_browser_session


def import_cookies(source: Path, destination: Path, user_agent: str) -> int:
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different files")
    data = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("cookies")
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of browser cookies")
    cookies = []
    for item in data:
        if not isinstance(item, dict) or not ozon_cookie_domain(item.get("domain")):
            continue
        cookie = {
            key: item[key]
            for key in ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite")
            if key in item
        }
        cookie["expires"] = item.get("expirationDate", item.get("expires", item.get("expiry", -1)))
        cookies.append(cookie)
    if not cookies:
        raise ValueError("No Ozon cookies in browser export")
    # Validate using the same rules as the actual HTTP client before writing a session file.
    # The cookie values never appear in logs or error output.
    with tempfile.TemporaryDirectory() as temp_dir:
        candidate = Path(temp_dir) / "cookies.json"
        save_browser_session(candidate, cookies, user_agent)
        with product_session(str(candidate)) as session:
            count = len(session.cookies)
    if destination.is_dir():
        raise ValueError(f"{destination} is a directory; remove the empty directory with rmdir")
    save_browser_session(destination, cookies, user_agent)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path, help="Local JSON browser cookie export")
    parser.add_argument(
        "--user-agent", required=True, help="navigator.userAgent from the same browser"
    )
    parser.add_argument("--output", type=Path, default=Path("cookies.json"))
    args = parser.parse_args()
    try:
        count = import_cookies(args.export, args.output, args.user_agent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Cookie import failed: {exc}\n")
    print(f"Saved local session with {count} usable Ozon cookies to {args.output}")


if __name__ == "__main__":
    main()
