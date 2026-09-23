import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

LOGGER = logging.getLogger(__name__)
DEFAULT_CDP_ENDPOINT = "http://127.0.0.1:9222"
DEFAULT_PROFILE = Path.home() / ".cache" / "ozon-parser-chrome"


def cdp_is_ready(endpoint: str) -> bool:
    try:
        with urlopen(f"{endpoint.rstrip('/')}/json/version", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError, ValueError):
        return False


def _local_cdp_port(endpoint: str) -> int:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError(
            "Automatic Chrome startup supports only a local HTTP OZON_CDP_ENDPOINT"
        )
    return parsed.port or 80


def _chrome_executable() -> str:
    configured = os.getenv("OZON_CHROME_EXECUTABLE", "").strip()
    if configured:
        if Path(configured).is_file():
            return configured
        raise RuntimeError(f"OZON_CHROME_EXECUTABLE does not exist: {configured}")

    for name in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(name)
        if executable:
            return executable
    raise RuntimeError(
        "Google Chrome/Chromium was not found. Set OZON_CHROME_EXECUTABLE in .env."
    )


def ensure_cdp_browser(endpoint: str, *, start_url: str) -> bool:
    endpoint = endpoint.strip()
    if cdp_is_ready(endpoint):
        LOGGER.info("Reusing Chrome CDP session at %s", endpoint)
        return False

    port = _local_cdp_port(endpoint)
    profile_value = os.getenv("OZON_CHROME_PROFILE", "").strip() or str(DEFAULT_PROFILE)
    profile = Path(profile_value).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    executable = _chrome_executable()
    LOGGER.info("Chrome CDP is unavailable; starting %s", executable)
    process = subprocess.Popen(
        [
            executable,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile}",
            start_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if cdp_is_ready(endpoint):
            LOGGER.info("Chrome CDP is ready at %s", endpoint)
            return True
        if process.poll() is not None:
            raise RuntimeError(
                "Chrome exited before CDP became ready. Close any Chrome using the "
                "same OZON_CHROME_PROFILE and retry."
            )
        time.sleep(0.25)

    raise RuntimeError(f"Chrome CDP did not become ready at {endpoint} within 20 seconds")
