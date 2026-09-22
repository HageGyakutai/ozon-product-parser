import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "inspect_product_html", ROOT / "scripts" / "inspect_product_html.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_inspector_outputs_structure_without_values():
    secret = "DO_NOT_PRINT_SECRET_VALUE"
    html = f"""
    <script type="application/ld+json">
    {{
      "@type": "Product",
      "sku": "123",
      "name": "Example",
      "image": ["https://example.invalid/{secret}.jpg"],
      "characteristics": [
        {{"name": "Цвет", "value": "{secret}"}}
      ],
      "richContent": {{"blocks": [{{"image": "{secret}"}}]}}
    }}
    </script>
    """

    output = "\n".join(MODULE.inspect_html(html, "123"))

    assert "MATCH" in output
    assert "CHARACTERISTIC" in output
    assert "key=richContent" in output
    assert "key=image" in output
    assert secret not in output
