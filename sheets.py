"""Small, dependency-light Google Sheets v4 adapter.

The adapter deliberately uses the REST API instead of ``google-api-python-client``.
That keeps the production dependency surface small and makes the HTTP boundary easy
to fake in tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import requests

from models import Lead, REQUIRED_COLUMNS


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
API_ROOT = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(RuntimeError):
    """A safe, user-facing Sheets adapter error."""


class SheetSchemaError(SheetsError):
    pass


class LeadNotFoundError(SheetsError):

    pass


class AmbiguousLeadError(SheetsError):
    pass


def _normalise_header(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be positive")
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _safe_detail(response: Any) -> str:
    """Return a useful API error without echoing request credentials."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message")
        if message:
            return str(message)[:500]
    except Exception:
        pass
    return f"HTTP {getattr(response, 'status_code', 'error')}"


class Sheets:
    """Read leads and update rows in one Google Sheet.

    ``session`` and ``credentials`` are injectable so unit tests never need network
    access or real credentials.
    """

    def __init__(
        self,
        config: Any,
        *,
        session: Any | None = None,
        credentials: Any | None = None,
        mandatory_headers: Iterable[str] = REQUIRED_COLUMNS,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self._credentials = credentials
        self.mandatory_headers = tuple(mandatory_headers)
        self.sheet_id = str(config.google_sheet_id)
        self.sheet_name = str(config.google_sheet_name)
        self.timeout = float(getattr(config, "http_timeout", 20))

    def _get_credentials(self) -> Any:
        if self._credentials is not None:
            return self._credentials
        service_account_value = getattr(self.config, "google_service_account_json", "")
        if service_account_value:
            try:
                from google.oauth2 import service_account

                raw = str(service_account_value).strip()
                if raw.startswith("{"):
                    info = json.loads(raw)
                else:
                    info = json.loads(Path(raw).read_text(encoding="utf-8"))
                self._credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=[SHEETS_SCOPE]
                )
                return self._credentials
            except Exception:
                raise SheetsError("Google service-account credentials are invalid") from None

        refresh_token = getattr(self.config, "google_oauth_refresh_token", "")
        client_id = getattr(self.config, "google_oauth_client_id", "")
        client_secret = getattr(self.config, "google_oauth_client_secret", "")
        if refresh_token and client_id and client_secret:
            try:
                from google.oauth2.credentials import Credentials

                self._credentials = Credentials(
                    token=None,
                    refresh_token=refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=[SHEETS_SCOPE],
                )
                return self._credentials
            except Exception:
                raise SheetsError("Google OAuth credentials are invalid") from None
        raise SheetsError("Google Sheets credentials are not configured")

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}) or {})
        credentials = self._get_credentials()
        try:
            if not getattr(credentials, "valid", False):
                from google.auth.transport.requests import Request

                credentials.refresh(Request(session=self.session))
            credentials.apply(headers)
            response = self.session.request(
                method,
                f"{API_ROOT}/{quote(self.sheet_id, safe='')}/{path}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except SheetsError:
            raise
        except Exception:
            raise SheetsError("Google Sheets request failed") from None
        if not 200 <= response.status_code < 300:
            raise SheetsError(f"Google Sheets request failed: {_safe_detail(response)}")
        return response

    def _range(self, cells: str) -> str:
        title = self.sheet_name.replace("'", "''")
        return f"'{title}'!{cells}"

    def _sheet_range(self) -> str:
        """A1 reference for the whole existing grid without guessing its width."""
        title = self.sheet_name.replace("'", "''")
        return f"'{title}'"

    def _values(self) -> list[list[Any]]:
        encoded = quote(self._sheet_range(), safe="")
        response = self._request(
            "GET", f"values/{encoded}", params={"majorDimension": "ROWS"}
        )
        try:
            values = response.json().get("values", [])
        except Exception:
            raise SheetsError("Google Sheets returned invalid JSON") from None
        if not isinstance(values, list):
            raise SheetsError("Google Sheets returned invalid values")
        return values

    def _table(self) -> tuple[list[str], list[Lead]]:
        rows = self._values()
        if not rows:
            raise SheetSchemaError("The sheet is empty")
        headers = [str(item).strip() for item in rows[0]]
        normalised = [_normalise_header(item) for item in headers]
        duplicates = sorted({name for name in normalised if name and normalised.count(name) > 1})
        if duplicates:
            raise SheetSchemaError(f"Duplicate sheet headers: {', '.join(duplicates)}")
        missing = [name for name in self.mandatory_headers if _normalise_header(name) not in normalised]
        if missing:
            raise SheetSchemaError(f"Missing mandatory sheet headers: {', '.join(missing)}")
        leads: list[Lead] = []
        for row_number, row in enumerate(rows[1:], start=2):
            values = {
                header: str(row[index]) if index < len(row) and row[index] is not None else ""
                for index, header in enumerate(headers)
                if header
            }
            if any(value.strip() for value in values.values()):
                leads.append(Lead(row_number=row_number, values=values))
        return headers, leads

    def read_leads(self) -> list[Lead]:
        """Return non-empty data rows after validating the header row."""
        return self._table()[1]

    # Common alternative name retained for integrations that call list_leads().
    list_leads = read_leads

    def update_lead(self, lead: Lead | str, updates: Mapping[str, Any]) -> Lead:
        """Update a lead selected by its stable key using fresh sheet contents.

        The row number on a previously read ``Lead`` is intentionally ignored: rows
        may have moved since the read. Duplicate keys fail closed.
        """
        key = str(lead.key if isinstance(lead, Lead) else lead).strip()
        if not key:
            raise ValueError("lead key must not be empty")
        headers, fresh_leads = self._table()
        matches = [candidate for candidate in fresh_leads if str(candidate.key).strip() == key]
        if not matches:
            raise LeadNotFoundError(f"Lead key was not found: {key}")
        if len(matches) != 1:
            raise AmbiguousLeadError(f"Lead key is duplicated: {key}")

        header_by_normalised = {_normalise_header(header): (index, header) for index, header in enumerate(headers)}
        data = []
        resolved: dict[str, str] = {}
        for requested_header, value in updates.items():
            found = header_by_normalised.get(_normalise_header(requested_header))
            if found is None:
                raise SheetSchemaError(f"Unknown sheet header: {requested_header}")
            index, actual_header = found
            cell = f"{_column_name(index + 1)}{matches[0].row_number}"
            data.append({"range": self._range(cell), "values": [["" if value is None else value]]})
            resolved[actual_header] = "" if value is None else str(value)

        if data:
            self._request(
                "POST",
                "values:batchUpdate",
                json={"valueInputOption": "RAW", "data": data},
            )
        new_values = dict(matches[0].values)
        new_values.update(resolved)
        return Lead(row_number=matches[0].row_number, values=new_values)

    def healthcheck(self) -> dict[str, int | str]:
        """Verify read access and schema without mutating the spreadsheet."""
        headers, leads = self._table()
        return {
            "sheet_name": self.sheet_name,
            "rows": len(leads),
            "columns": len(headers),
        }


GoogleSheetsAdapter = Sheets
