"""Inspect saved Ozon HTML structure without printing field values or secrets."""

import argparse
import json
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup

from ozon_parser.extractor import decode_nested_json

JSON_SCRIPT_SELECTOR = (
    'script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__'
)

INTERESTING_KEY = re.compile(
    r"(photo|video|gallery|media|image|rich|content|character|attribute|material|color|sku|product)",
    re.I,
)
SCRIPT_KEYWORDS = {
    "photo": re.compile(r"photo", re.I),
    "video": re.compile(r"video", re.I),
    "gallery": re.compile(r"gallery", re.I),
    "media": re.compile(r"media", re.I),
    "rich": re.compile(r"rich.?content|richContent", re.I),
    "characteristics": re.compile(r"characteristic|attribute", re.I),
    "color": re.compile(r'(?:"|\b)(?:color|цвет)(?:"|\b)', re.I),
    "material": re.compile(r'(?:"|\b)(?:material|материал)(?:"|\b)', re.I),
    "art_set": re.compile(
        r"артикул производителя|art.?set|комплектация|состав набора",
        re.I,
    ),
}
CHARACTERISTIC_LABELS = {
    "цвет",
    "color",
    "материал",
    "material",
    "артикул производителя",
    "art set",
    "комплектация",
    "состав набора",
}


def walk_paths(node, path: str = "$") -> Iterator[tuple[str, object]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk_paths(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk_paths(value, f"{path}[{index}]")


def value_type(value: object) -> str:
    if isinstance(value, dict):
        return f"dict[{len(value)}]"
    if isinstance(value, list):
        return f"list[{len(value)}]"
    return type(value).__name__


def _script_type(script) -> str:
    raw = script.get("type")
    return raw.strip().lower() if isinstance(raw, str) and raw.strip() else "(none)"


def _safe_dom_path(element) -> str:
    parts = []
    current = element
    while current is not None and getattr(current, "name", None) and len(parts) < 6:
        parent = current.parent
        if parent is None or not getattr(parent, "find_all", None):
            parts.append(current.name)
            break
        siblings = parent.find_all(current.name, recursive=False)
        if len(siblings) > 1:
            index = siblings.index(current) + 1
            parts.append(f"{current.name}:nth-of-type({index})")
        else:
            parts.append(current.name)
        current = parent
    return " > ".join(reversed(parts))


def _try_json_script(script):
    text = script.string or script.get_text()
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return decode_nested_json(json.loads(stripped))
    except (ValueError, TypeError):
        return None


def inspect_html(html: str, sku: str, max_lines: int = 350) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = list(soup.find_all("script"))
    script_types = Counter(_script_type(script) for script in scripts)

    parsed_scripts = []
    for script_index, script in enumerate(scripts):
        parsed = _try_json_script(script)
        if parsed is not None:
            parsed_scripts.append((script_index, parsed))

    lines = [
        f"total_scripts={len(scripts)}",
        f"parseable_scripts={len(parsed_scripts)}",
        "script_types="
        + ",".join(f"{name}:{count}" for name, count in sorted(script_types.items())),
        f"dom_img_count={len(soup.find_all('img'))}",
        f"dom_video_count={len(soup.find_all('video'))}",
        f"sku_occurrences_in_html={html.count(sku)}",
    ]
    emitted = set()

    def emit(line: str) -> None:
        if line not in emitted and len(lines) < max_lines:
            emitted.add(line)
            lines.append(line)

    for script_index, state in parsed_scripts:
        for path, node in walk_paths(state):
            if not isinstance(node, dict):
                continue

            source_sku = node.get("sku") or node.get("productId")
            if source_sku is not None and str(source_sku) == sku:
                keys = ",".join(sorted(str(key) for key in node))
                product_type = node.get("@type")
                suffix = " type=Product" if product_type == "Product" else ""
                emit(f"MATCH script={script_index} path={path}{suffix} keys={keys}")

            label = node.get("name", node.get("title"))
            if isinstance(label, str) and label.casefold().strip() in CHARACTERISTIC_LABELS:
                keys = ",".join(sorted(str(key) for key in node))
                emit(
                    f"CHARACTERISTIC script={script_index} path={path} "
                    f"label={label.casefold().strip()} keys={keys}"
                )

            for key, value in node.items():
                if INTERESTING_KEY.search(str(key)):
                    emit(
                        f"KEY script={script_index} path={path} "
                        f"key={key} value_type={value_type(value)}"
                    )

    # Inspect every script, including non-JSON application state, without printing its contents.
    for script_index, script in enumerate(scripts):
        text = script.string or script.get_text()
        if not text:
            continue
        hits = [name for name, pattern in SCRIPT_KEYWORDS.items() if pattern.search(text)]
        contains_sku = sku in text
        if hits or contains_sku:
            emit(
                f"SCRIPT_SCAN script={script_index} type={_script_type(script)} "
                f"contains_sku={str(contains_sku).lower()} keywords={','.join(hits) or '-'}"
            )

    # Look for rendered characteristic labels without printing adjacent values.
    for element in soup.find_all(string=True):
        normalized = " ".join(str(element).split()).casefold()
        if normalized not in CHARACTERISTIC_LABELS:
            continue
        parent = element.parent
        if parent is None:
            continue
        attrs = ",".join(sorted(parent.attrs))
        emit(
            f"DOM_LABEL label={normalized} tag={parent.name} "
            f"path={_safe_dom_path(parent)} attrs={attrs or '-'}"
        )

    # Report only names of interesting DOM attributes, never their values.
    for element in soup.find_all(True):
        interesting_attrs = [
            name
            for name in element.attrs
            if INTERESTING_KEY.search(str(name)) or str(name).startswith("data-")
        ]
        if interesting_attrs:
            emit(
                f"DOM_ATTR tag={element.name} path={_safe_dom_path(element)} "
                f"attrs={','.join(sorted(interesting_attrs))}"
            )

    # Global presence counters are useful when a value is rendered as text but not structured JSON.
    for name, pattern in SCRIPT_KEYWORDS.items():
        count = len(pattern.findall(html))
        if count:
            emit(f"HTML_MARKER name={name} occurrences={count}")

    if len(lines) >= max_lines:
        lines.append(f"output_truncated_at={max_lines}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_file", type=Path)
    parser.add_argument("sku", help="Expected numeric Ozon SKU")
    parser.add_argument("--max-lines", type=int, default=350)
    args = parser.parse_args()

    if not args.sku.isascii() or not args.sku.isdecimal():
        parser.error("SKU must contain ASCII digits")
    if args.max_lines < 20 or args.max_lines > 2000:
        parser.error("--max-lines must be between 20 and 2000")

    try:
        html = args.html_file.read_text(encoding="utf-8")
    except OSError as exc:
        parser.exit(2, f"Cannot read HTML: {exc}\n")

    for line in inspect_html(html, args.sku, args.max_lines):
        print(line)


if __name__ == "__main__":
    main()
