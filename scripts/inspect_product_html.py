"""Inspect structural JSON paths in a saved Ozon HTML page without printing field values."""

import argparse
import json
import re
from collections.abc import Iterator
from pathlib import Path

from bs4 import BeautifulSoup

from ozon_parser.extractor import decode_nested_json

SCRIPT_SELECTOR = (
    'script[type="application/ld+json"], '
    'script[type="application/json"], '
    'script#__NEXT_DATA__'
)

INTERESTING_KEY = re.compile(
    r"(photo|video|gallery|media|image|rich|content|character|attribute|material|color|sku|product)",
    re.I,
)
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


def inspect_html(html: str, sku: str, max_lines: int = 250) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    states = []
    for script_index, script in enumerate(soup.select(SCRIPT_SELECTOR)):
        try:
            parsed = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        states.append((script_index, decode_nested_json(parsed)))

    lines = [f"parseable_scripts={len(states)}"]
    emitted = set()

    def emit(line: str) -> None:
        if line not in emitted and len(lines) < max_lines:
            emitted.add(line)
            lines.append(line)

    for script_index, state in states:
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

    if len(lines) >= max_lines:
        lines.append(f"output_truncated_at={max_lines}")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_file", type=Path)
    parser.add_argument("sku", help="Expected numeric Ozon SKU")
    parser.add_argument("--max-lines", type=int, default=250)
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
