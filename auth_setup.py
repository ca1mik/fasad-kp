"""Interactive helpers for obtaining Google OAuth refresh credentials.

This module is never imported by the runtime adapters.  Run it locally when initial
OAuth consent is needed; production uses the resulting environment values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
GMAIL_SCOPE = "https://mail.google.com/"


class AuthSetupError(RuntimeError):
    pass


def obtain_google_refresh_token(
    client_id: str,
    client_secret: str,
    scopes: Iterable[str],
    *,
    port: int = 0,
    open_browser: bool = True,
) -> str:
    """Run Google's installed-application consent flow and return a refresh token."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            },
            scopes=list(scopes),
        )
        credentials = flow.run_local_server(
            port=port,
            open_browser=open_browser,
            access_type="offline",
            prompt="consent",
        )
    except Exception:
        raise AuthSetupError("Google OAuth authorization did not complete") from None
    if not credentials.refresh_token:
        raise AuthSetupError(
            "Google did not issue a refresh token; revoke prior consent and try again"
        )
    return str(credentials.refresh_token)


def validate_service_account(path_or_json: str) -> str:
    """Validate a service-account JSON value and return its client email."""
    try:
        value = path_or_json.strip()
        info: Any = json.loads(value) if value.startswith("{") else json.loads(
            Path(value).read_text(encoding="utf-8")
        )
        required = {"client_email", "private_key", "token_uri"}
        if not isinstance(info, dict) or not required.issubset(info):
            raise ValueError
        return str(info["client_email"])
    except Exception:
        raise AuthSetupError("Service-account JSON is invalid or incomplete") from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create OAuth credentials for the Sheets/mail adapters"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    google = subparsers.add_parser("google-oauth", help="Run Google local consent")
    google.add_argument("--client-id", required=True)
    google.add_argument("--client-secret", required=True)
    google.add_argument(
        "--purpose", choices=("sheets", "mail", "both"), default="both"
    )
    google.add_argument("--port", type=int, default=0)
    google.add_argument("--no-browser", action="store_true")
    service = subparsers.add_parser(
        "check-service-account", help="Validate service-account JSON"
    )
    service.add_argument("value", help="JSON text or path to a JSON file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check-service-account":
        email = validate_service_account(args.value)
        print(f"Valid service account: {email}")
        return 0
    scopes = {
        "sheets": [SHEETS_SCOPE],
        "mail": [GMAIL_SCOPE],
        "both": [SHEETS_SCOPE, GMAIL_SCOPE],
    }[args.purpose]
    refresh_token = obtain_google_refresh_token(
        args.client_id,
        args.client_secret,
        scopes,
        port=args.port,
        open_browser=not args.no_browser,
    )
    # This command is intentionally interactive. The token is printed once so the
    # operator can place it in a secret store; runtime logs never contain it.
    print("OAuth refresh token (store as a secret):")
    print(refresh_token)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by an operator
    raise SystemExit(main())
