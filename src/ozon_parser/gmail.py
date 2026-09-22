"""Read verification messages received after the current login attempt."""

import base64
import re
import time
from datetime import UTC, datetime
from pathlib import Path


def verification_code(text: str) -> str | None:
    match = re.search(r"(?:код|code)[^\d]{0,50}(\d{4,8})\b", text, re.I)
    return match.group(1) if match else None


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
            credentials = InstalledAppFlow.from_client_secrets_file(
                credentials_file, scopes
            ).run_local_server(port=0)
        token.write_text(credentials.to_json(), encoding="utf-8")
        token.chmod(0o600)
    return build("gmail", "v1", credentials=credentials)


def wait_for_code(service, since: datetime, timeout: int = 180, interval: int = 5) -> str:
    cutoff = int(since.astimezone(UTC).timestamp() * 1000)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=f"after:{cutoff // 1000} ozon", maxResults=20)
            .execute()
        )
        for item in result.get("messages", []):
            message = (
                service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            )
            if int(message.get("internalDate", 0)) < cutoff:
                continue
            headers = {
                h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])
            }
            if "ozon" not in (headers.get("from", "") + headers.get("subject", "")).lower():
                continue
            chunks = [message.get("snippet", "")]

            def collect(part, chunks=chunks):
                encoded = part.get("body", {}).get("data")
                if encoded and part.get("mimeType") in ("text/plain", "text/html"):
                    chunks.append(
                        base64.urlsafe_b64decode(encoded + "===").decode("utf-8", errors="replace")
                    )
                for child in part.get("parts", []):
                    collect(child)

            collect(message.get("payload", {}))
            for chunk in chunks:
                code = verification_code(chunk)
                if code:
                    return code
        time.sleep(interval)
    raise TimeoutError("No new Ozon verification email with code within timeout")
