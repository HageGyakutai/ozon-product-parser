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
    <html>
      <body>
        <div data-widget="characteristics">
          <span>Цвет</span><span>{secret}</span>
        </div>
        <img src="https://example.invalid/{secret}.jpg">
        <script type="application/ld+json">
        {{
          "@type": "Product",
          "sku": "123",
          "name": "Example",
          "image": ["https://example.invalid/{secret}.jpg"]
        }}
        </script>
        <script>
          window.__state__ = {{
            "sku": "123",
            "richContent": {{"image": "{secret}"}},
            "material": "{secret}",
            "videoGallery": ["{secret}"]
          }};
        </script>
      </body>
    </html>
    """

    output = "\n".join(MODULE.inspect_html(html, "123"))

    assert "MATCH" in output
    assert "key=image" in output
    assert "SCRIPT_SCAN" in output
    assert "SCRIPT_KEYS" in output
    assert "keywords=video,gallery,media,rich,material" in output or "material" in output
    assert "DOM_LABEL label=цвет" in output
    assert "DOM_WIDGETS" in output or "dom_indexed_nodes=" in output
    assert "HTML_MARKER name=rich" in output
    assert secret not in output


def test_inspector_parses_json_scripts_without_declared_json_type():
    html = """
    <script>
    {"productId": "321", "title": "Example", "color": "red"}
    </script>
    """

    output = "\n".join(MODULE.inspect_html(html, "321"))

    assert "parseable_scripts=1" in output
    assert "MATCH script=0" in output
    assert "key=color" in output


def test_inspector_reports_widget_structure():
    html = """
    <html><body>
      <div data-widget="webGallery">
        <div data-index="0"><img src="a.jpg"></div>
        <div data-index="1"><img src="b.jpg"></div>
      </div>
      <div data-widget="richTextWidget">
        <table><tr><td>Example</td></tr></table>
      </div>
      <script type="application/ld+json">
      {"@type": "Product", "sku": "123", "name": "Example"}
      </script>
    </body></html>
    """

    output = "\n".join(MODULE.inspect_html(html, "123"))

    assert "WIDGET_DETAIL name=webGallery occurrence=1 img=2" in output
    assert "indexed=2" in output
    assert "WIDGET_DETAIL name=richTextWidget occurrence=1" in output
    assert "table=1" in output
