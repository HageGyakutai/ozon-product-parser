"""Create a restricted, best-effort redacted HTML snapshot for local debugging."""

import json
import os
import re
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

SECRET_KEY = re.compile(
    r"cookie|token|authorization|session|email|phone|password|credential|verification|otp|csrf",
    re.I,
)
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE = re.compile(
    r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s()\-]*\d{2}[\s()\-]*\d{2}(?!\d)"
)


def redact_text(value: str) -> str:
    return PHONE.sub("[REDACTED PHONE]", EMAIL.sub("[REDACTED EMAIL]", value))


def redact_json(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SECRET_KEY.search(str(key)) else redact_json(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                nested = json.loads(value)
            except ValueError:
                pass
            else:
                if isinstance(nested, (dict, list)):
                    return json.dumps(redact_json(nested), ensure_ascii=False)
        return redact_text(value)
    return value


def sanitized_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select("script, style, iframe, form, meta, input"):
        if element.name == "script" and (
            element.get("type") in ("application/json", "application/ld+json")
            or element.get("id") == "__NEXT_DATA__"
        ):
            try:
                state = json.loads(element.string or element.get_text())
            except (TypeError, ValueError):
                element.decompose()
            else:
                element.clear()
                element.append(json.dumps(redact_json(state), ensure_ascii=False))
        else:
            element.decompose()
    for element in soup.find_all(True):
        for name in list(element.attrs):
            if name not in ("class", "id") and not (element.name == "script" and name == "type"):
                del element.attrs[name]
    return redact_text(str(soup))


def save_debug_html(path: Path, html: str) -> None:
    """Save a redacted snapshot with owner-only permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
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
            handle.write(sanitized_html(html))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
