"""Portable browser session data shared by the login and product clients."""

import json
import os
import tempfile
from pathlib import Path


def ozon_cookie_domain(domain: object) -> bool:
    if not isinstance(domain, str):
        return False
    normalized = domain.lstrip(".").lower()
    return normalized == "ozon.ru" or normalized.endswith(".ozon.ru")


def save_browser_session(path: Path, cookies: list[dict], user_agent: str) -> None:
    """Write secrets with restricted permissions and replace the old file atomically."""
    if not user_agent or not user_agent.strip():
        raise ValueError("Browser User-Agent is missing")
    if path.is_dir():
        raise ValueError(f"{path} is a directory; remove or rename it before saving cookies")
    payload = {"version": 1, "user_agent": user_agent, "cookies": cookies}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(payload, handle)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
