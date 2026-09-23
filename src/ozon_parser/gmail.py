"""Read verification messages received after the current login attempt."""

import base64
import binascii
import logging
import os
import re
import time
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path

from bs4 import BeautifulSoup

CODE_AFTER_LABEL = re.compile(r"\b(?:код|code)\b[^\d]{0,50}(\d{4,8})\b", re.I)
CODE_BEFORE_LABEL = re.compile(r"\b(\d{4,8})\s*[-—:]?\s*(?:код|code)\b", re.I)


def verification_code(text: str) -> str | None:
    match = CODE_AFTER_LABEL.search(text) or CODE_BEFORE_LABEL.search(text)
    return match.group(1) if match else None


def trusted_sender(value: str, domains: tuple[str, ...]) -> bool:
    address = parseaddr(value)[1].lower()
    if address.count("@") != 1:
        return False
    domain = address.rsplit("@", 1)[1]
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in domains)


def message_text(payload: dict) -> list[str]:
    """Extract text parts from the Gmail API's nested MIME payload."""
    chunks = []
    kind = payload.get("mimeType")
    encoded = payload.get("body", {}).get("data")
    if kind in ("text/plain", "text/html") and isinstance(encoded, str):
        try:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            decoded = raw.decode("utf-8", errors="replace")
            if kind == "text/html":
                decoded = BeautifulSoup(decoded, "html.parser").get_text(" ")
            chunks.append(decoded)
        except (ValueError, binascii.Error):
            pass
    for part in payload.get("parts", []):
        if isinstance(part, dict):
            chunks.extend(message_text(part))
    return chunks


def gmail_service(credentials_file: str, token_file: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    if not Path(credentials_file).exists():
        raise FileNotFoundError("Gmail OAuth credentials missing; see README")
    token = Path(token_file)
    credentials = (
        Credentials.from_authorized_user_file(str(token), scopes) if token.exists() else None
    )
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            # The OAuth callback URL contains a one-time authorization code.
            # google-auth-oauthlib logs the raw HTTP request at INFO level.
            logging.getLogger("google_auth_oauthlib.flow").setLevel(logging.WARNING)
            credentials = InstalledAppFlow.from_client_secrets_file(
                credentials_file, scopes
            ).run_local_server(port=0, open_browser=not bool(os.getenv("WSL_DISTRO_NAME")))
        token.write_text(credentials.to_json(), encoding="utf-8")
        token.chmod(0o600)
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def wait_for_code(
    service,
    since: datetime,
    timeout: int = 180,
    interval: int = 5,
    *,
    query: str | None = None,
    sender_domains: tuple[str, ...] | None = None,
) -> str:
    if since.tzinfo is None:
        raise ValueError("since must include timezone")
    if timeout <= 0 or interval <= 0:
        raise ValueError("timeout and interval must be positive")
    if sender_domains is None:
        sender_domains = tuple(
            domain.strip().lower()
            for domain in os.getenv("GMAIL_SENDER_DOMAINS", "ozon.ru").split(",")
            if domain.strip()
        )
    if not sender_domains or any(
        not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", domain) for domain in sender_domains
    ):
        raise ValueError("GMAIL_SENDER_DOMAINS must list valid DNS domains")
    if query is None:
        query = os.getenv("GMAIL_QUERY", "ozon")
    cutoff = int(since.astimezone(UTC).timestamp() * 1000)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=f"after:{cutoff // 1000} {query}".strip(), maxResults=20)
            .execute()
        )
        for item in result.get("messages", []):
            message = (
                service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            )
            try:
                received_at = int(message.get("internalDate", 0))
            except (ValueError, TypeError):
                continue
            if received_at < cutoff:
                continue
            headers = {
                h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])
            }
            if not trusted_sender(headers.get("from", ""), sender_domains):
                continue
            chunks = message_text(message.get("payload", {}))
            if not chunks and isinstance(message.get("snippet"), str):
                chunks = [message["snippet"]]
            for chunk in chunks:
                code = verification_code(chunk)
                if code:
                    return code
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    raise TimeoutError("No new Ozon verification email with code within timeout")
