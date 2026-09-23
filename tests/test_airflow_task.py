"""Tests for the command executed by the Airflow DAG."""

import subprocess
import sys

import pytest

from ozon_parser import airflow_task


def test_airflow_skus_uses_task_examples_by_default():
    assert airflow_task.airflow_skus(None) == ["2359066702", "2829800382"]


def test_airflow_skus_accepts_commas_and_whitespace():
    assert airflow_task.airflow_skus("123, 456\n789") == ["123", "456", "789"]


def test_airflow_skus_rejects_invalid_values():
    with pytest.raises(ValueError, match="numeric SKU"):
        airflow_task.airflow_skus("123 invalid")


def test_run_daily_parser_reuses_existing_cli(monkeypatch):
    captured = {}

    def fake_run(command, **options):
        captured["command"] = command
        captured["options"] = options

    monkeypatch.setenv("OZON_AIRFLOW_SKUS", "123,456")
    monkeypatch.setattr(airflow_task.subprocess, "run", fake_run)

    airflow_task.run_daily_parser()

    assert captured["command"] == [
        sys.executable,
        str(airflow_task.PROJECT_ROOT / "scripts" / "parse_ozon.py"),
        "123",
        "456",
        "--transport",
        "browser",
        "--output",
        "database",
    ]
    assert captured["options"]["cwd"] == airflow_task.PROJECT_ROOT
    assert captured["options"]["check"] is True
