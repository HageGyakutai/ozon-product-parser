import json
from types import SimpleNamespace

import pytest

from ozon_parser.client import fetch_product, product_session


def test_cookie_domains_are_checked_at_label_boundary(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"domain": "fakeozon.ru", "name": "bad", "value": "bad"},
                {"domain": ".ozon.ru", "name": "good", "value": "ok"},
            ]
        ),
        encoding="utf-8",
    )
    session = product_session(str(path))
    try:
        assert [cookie.name for cookie in session.cookies] == ["good"]
    finally:
        session.close()


def test_antibot_html_is_not_treated_as_product():
    response = SimpleNamespace(
        status_code=200,
        url="https://www.ozon.ru/product/123/",
        text="<html><title>Antibot Challenge Page</title></html>",
        raise_for_status=lambda: None,
    )
    session = SimpleNamespace(get=lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="blocked access"):
        fetch_product(session, "123")
