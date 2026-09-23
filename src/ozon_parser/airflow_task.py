"""Run the existing parser as an Airflow task without duplicating parser logic."""

import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKUS = ("2359066702", "2829800382")


def airflow_skus(raw_value: str | None) -> list[str]:
    """Return validated SKU values from a comma- or whitespace-separated setting."""
    values = re.split(r"[,\s]+", raw_value.strip()) if raw_value and raw_value.strip() else []
    skus = [value for value in values if value] or list(DEFAULT_SKUS)
    if any(not sku.isascii() or not sku.isdecimal() for sku in skus):
        raise ValueError("OZON_AIRFLOW_SKUS must contain only numeric SKU values")
    return skus


def run_daily_parser() -> None:
    """Load project settings and execute the browser parser with database output."""
    load_dotenv(PROJECT_ROOT / ".env")
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "parse_ozon.py"),
        *airflow_skus(os.getenv("OZON_AIRFLOW_SKUS")),
        "--transport",
        "browser",
        "--output",
        "database",
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, env=os.environ.copy(), check=True)
