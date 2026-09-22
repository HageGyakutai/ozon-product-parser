import pytest

from ozon_parser.session_data import save_browser_session


def test_save_browser_session_rejects_directory_destination(tmp_path):
    destination = tmp_path / "cookies.json"
    destination.mkdir()

    with pytest.raises(ValueError, match=r"cookies\.json is a directory"):
        save_browser_session(
            destination,
            [{"domain": ".ozon.ru", "name": "sid", "value": "secret"}],
            "Test Browser UA",
        )

    assert destination.is_dir()
    assert list(destination.iterdir()) == []
