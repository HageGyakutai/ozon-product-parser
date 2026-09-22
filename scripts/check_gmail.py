"""Check Gmail OAuth and optionally wait for a new Ozon code without printing it."""

import argparse
import logging
import os
from datetime import UTC, datetime

from dotenv import load_dotenv

from ozon_parser.gmail import gmail_service, wait_for_code


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wait-for-code",
        action="store_true",
        help="Wait for a fresh Ozon message after starting this command; never print the code",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Seconds to wait (default: 180)")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    try:
        service = gmail_service(
            os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json"),
            os.getenv("GMAIL_TOKEN_FILE", "token.json"),
        )
        # Confirms that the OAuth token works for the intended Gmail account.
        service.users().getProfile(userId="me").execute()
        logging.info("Gmail API access confirmed; OAuth token is usable")
        if args.wait_for_code:
            started = datetime.now(UTC)
            logging.info("Waiting for a new Ozon verification email")
            wait_for_code(service, started, timeout=args.timeout)
            logging.info("New Ozon verification code found (value hidden)")
    except (FileNotFoundError, ValueError, TimeoutError) as exc:
        logging.error("Gmail check failed: %s", exc)
        return 1
    except Exception:
        logging.error("Gmail API request failed; check account access and OAuth configuration")
        return 1
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # The OAuth library both logs and prints the same authorization URL.
    logging.getLogger("google_auth_oauthlib.flow").setLevel(logging.WARNING)
    raise SystemExit(main())
