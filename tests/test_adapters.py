from __future__ import annotations

from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from mailer import Mailer, MailerError
from models import REQUIRED_COLUMNS
from sheets import AmbiguousLeadError, SheetSchemaError, Sheets


class FakeCredentials:
    valid = True

    def apply(self, headers):
        headers["Authorization"] = "Bearer test-token"


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeHTTPSession:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "GET":
            return FakeResponse({"values": self.rows})
        return FakeResponse({"updatedCells": 1})


def sheet_config():
    return SimpleNamespace(
        google_sheet_id="sheet-id",
        google_sheet_name="Leads & sales",
        google_service_account_json="",
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_refresh_token="",
        http_timeout=5,
    )


def lead_row(email="hello@example.test", company="Acme"):
    row = [""] * len(REQUIRED_COLUMNS)
    row[REQUIRED_COLUMNS.index("E-mail")] = email
    row[0] = company
    return row


def test_sheets_validates_headers():
    adapter = Sheets(
        sheet_config(), session=FakeHTTPSession([["E-mail"]]), credentials=FakeCredentials()
    )
    with pytest.raises(SheetSchemaError, match="Missing mandatory"):
        adapter.read_leads()


def test_sheets_reads_whole_existing_grid_without_out_of_bounds_column_guess():
    session = FakeHTTPSession([list(REQUIRED_COLUMNS), lead_row()])
    adapter = Sheets(sheet_config(), session=session, credentials=FakeCredentials())
    adapter.read_leads()
    assert "%27Leads%20%26%20sales%27" in session.calls[0][1]
    assert "ZZZ" not in session.calls[0][1]


def test_sheets_refinds_row_by_key_and_uses_raw_batch_update():
    session = FakeHTTPSession([list(REQUIRED_COLUMNS), lead_row()])
    adapter = Sheets(sheet_config(), session=session, credentials=FakeCredentials())
    lead = adapter.read_leads()[0]
    # Simulate a row inserted after the initial read. update_lead must ignore the old row number.
    session.rows = [list(REQUIRED_COLUMNS), ["placeholder"], lead_row()]
    updated = adapter.update_lead(lead, {"E-mail": "new@example.test"})
    assert updated.row_number == 3
    method, _, kwargs = session.calls[-1]
    assert method == "POST"
    assert kwargs["json"]["valueInputOption"] == "RAW"
    assert kwargs["json"]["data"][0]["range"].endswith("D3")


def test_sheets_refuses_duplicate_stable_keys():
    session = FakeHTTPSession(
        [list(REQUIRED_COLUMNS), lead_row(), lead_row()]
    )
    adapter = Sheets(sheet_config(), session=session, credentials=FakeCredentials())
    lead = adapter.read_leads()[0]
    with pytest.raises(AmbiguousLeadError):
        adapter.update_lead(lead, {"E-mail": "new@example.test"})


def test_sheets_healthcheck_validates_schema_and_returns_dimensions():
    session = FakeHTTPSession([list(REQUIRED_COLUMNS), lead_row()])
    adapter = Sheets(sheet_config(), session=session, credentials=FakeCredentials())
    assert adapter.healthcheck() == {
        "sheet_name": "Leads & sales",
        "rows": 1,
        "columns": len(REQUIRED_COLUMNS),
    }


class FakeSMTP:
    instances = []

    def __init__(self, *args, **kwargs):
        self.sent = []
        self.logged_in = False
        self.__class__.instances.append(self)

    def ehlo(self):
        return 250, b"ok"

    def starttls(self, **kwargs):
        return 220, b"ready"

    def login(self, address, password):
        self.logged_in = (address, password)

    def send_message(self, message):
        self.sent.append(message)
        return {}

    def quit(self):
        pass


class FakeIMAP:
    instances = []
    messages = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.__class__.instances.append(self)

    def login(self, address, password):
        self.calls.append(("login", address, password))

    def select(self, folder, readonly=False):
        self.calls.append(("select", folder, readonly))
        return "OK", [b"1"]

    def uid(self, command, *args):
        self.calls.append(("uid", command, args))
        if command == "search":
            return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.messages)))]
        if b"," in args[0] or b"HEADER.FIELDS" in args[-1].encode():
            return "OK", [
                (b"1 (UID " + uid + b" BODY[HEADER] {1})", self.messages[int(uid) - 1])
                for uid in args[0].split(b",")
            ]
        uid = int(args[0])
        return "OK", [(b"1 (BODY[] {1})", self.messages[uid - 1])]

    def close(self):
        self.calls.append(("close",))

    def logout(self):
        self.calls.append(("logout",))


def mail_config():
    return SimpleNamespace(
        mail_provider="custom",
        mail_address="sales@example.test",
        mail_auth_mode="app_password",
        mail_app_password="secret-app-password",
        mail_display_name="Sales",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        imap_host="imap.example.test",
        imap_port=993,
        imap_folder="INBOX",
        oauth_client_id="",
        oauth_client_secret="",
        oauth_refresh_token="",
        oauth_token_url="",
        http_timeout=5,
    )


def adapter():
    FakeSMTP.instances.clear()
    FakeIMAP.instances.clear()
    return Mailer(
        mail_config(),
        smtp_factory=FakeSMTP,
        smtp_ssl_factory=FakeSMTP,
        imap_factory=FakeIMAP,
    )


def test_healthcheck_authenticates_and_opens_imap_read_only_without_sending():
    mailer = adapter()
    assert mailer.healthcheck()
    assert FakeSMTP.instances[0].sent == []
    assert ("select", "INBOX", True) in FakeIMAP.instances[0].calls


def test_send_uses_and_returns_predetermined_message_id_once():
    mailer = adapter()
    result = mailer.send(
        "buyer@example.test", "Hello", "Body", message_id="campaign-1@example.test"
    )
    assert result.message_id == "<campaign-1@example.test>"
    sent = FakeSMTP.instances[0].sent
    assert len(sent) == 1
    assert sent[0]["Message-ID"] == result.message_id


def test_fetch_replies_matches_references_and_uses_body_peek():
    reply = EmailMessage()
    reply["From"] = "Buyer <buyer@example.test>"
    reply["To"] = "sales@example.test"
    reply["Subject"] = "Re: Hello"
    reply["Message-ID"] = "<reply@example.test>"
    reply["In-Reply-To"] = "<campaign-1@example.test>"
    reply["References"] = "<older@example.test> <campaign-1@example.test>"
    reply["Date"] = "Tue, 22 Sep 2026 12:00:00 +0300"
    reply.set_content("Yes, please call me.")
    FakeIMAP.messages = [reply.as_bytes()]
    mailer = adapter()
    messages = mailer.fetch_replies(["<campaign-1@example.test>"])
    assert len(messages) == 1
    assert messages[0].from_address == "buyer@example.test"
    assert messages[0].references == (
        "<older@example.test>",
        "<campaign-1@example.test>",
    )
    uid_calls = [call for call in FakeIMAP.instances[0].calls if call[0] == "uid"]
    assert uid_calls[-1][2][-1] == "(BODY.PEEK[])"


def test_fetch_replies_reads_full_body_only_for_matching_reply():
    unrelated = EmailMessage()
    unrelated["Message-ID"] = "<unrelated@example.test>"
    unrelated.set_content("Unrelated")
    matching = EmailMessage()
    matching["Message-ID"] = "<reply@example.test>"
    matching["In-Reply-To"] = "<campaign-1@example.test>"
    matching.set_content("Interested")
    FakeIMAP.messages = [unrelated.as_bytes(), matching.as_bytes()]
    mailer = adapter()
    messages = mailer.fetch_replies(["<campaign-1@example.test>"], header_first=True)
    assert len(messages) == 1 and messages[0].body == "Interested\n"
    fetches = [call[2][-1] for call in FakeIMAP.instances[0].calls if call[:2] == ("uid", "fetch")]
    assert fetches.count("(BODY.PEEK[])") == 1
    assert fetches.count("(UID BODY.PEEK[HEADER.FIELDS (IN-REPLY-TO REFERENCES)])") == 1


def test_send_errors_are_sanitized_and_never_retry():
    class FailingSMTP(FakeSMTP):
        def send_message(self, message):
            self.sent.append(message)
            raise RuntimeError("server said secret-app-password")

    mailer = Mailer(
        mail_config(),
        smtp_factory=FailingSMTP,
        smtp_ssl_factory=FailingSMTP,
        imap_factory=FakeIMAP,
    )
    with pytest.raises(MailerError, match="outcome is uncertain") as error:
        mailer.send("buyer@example.test", "Hello", "Body")
    assert "secret-app-password" not in str(error.value)
    assert len(FailingSMTP.instances[-1].sent) == 1
