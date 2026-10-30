"""Authorize only Fasad Flow Gmail in the user's browser; never print secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gmail_https import oauth_module  # noqa: E402
from serbia_outreach import DATA, read_config, configured_bridge  # noqa: E402


def pick_client() -> Path | None:
    default = DATA / "gmail_oauth_client.json"
    if default.is_file():
        return default
    print("Нужен скачанный Google OAuth JSON типа Desktop app, не service account.")
    print("OAuth-клиент: https://console.cloud.google.com/auth/clients")
    print("Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com")
    print("Если JSON ещё нет: включите Gmail API, настройте аудиторию OAuth и создайте Desktop app клиент.")
    print("В режиме Testing добавьте koallalenivaa@gmail.com в Test users. Скачайте JSON и выберите его.")
    import tkinter
    from tkinter.filedialog import askopenfilename
    window = tkinter.Tk()
    window.withdraw()
    try:
        selected = askopenfilename(title="Fasad Flow: выберите Google OAuth Desktop app JSON",
                                   filetypes=[("Google OAuth client", "*.json")], parent=window)
        return Path(selected) if selected else None
    finally:
        window.destroy()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secrets", type=Path)
    args = parser.parse_args()
    try:
        config = read_config()
        if config["expected_sender"] != "koallalenivaa@gmail.com" or config.get("outbound_transport") != "gmail_https":
            raise ValueError("Unexpected authorized sender or transport")
        if config.get("mailbox_profile"):
            bridge = configured_bridge(config)
            with bridge.mailbox_guard():
                bridge.mailer.healthcheck()
            print(json.dumps({"sender": bridge.mailer.address, "oauth_authorized": True,
                              "existing_openclaw_profile": True, "test_emails_sent": 0}, ensure_ascii=False))
            return 0
        selected = args.client_secrets or pick_client()
        if selected is None:
            print("OAuth не подключён. Писем не отправлено. Пароль приложения сюда не нужен.")
            return 1
        DATA.mkdir(parents=True, exist_ok=True)
        result = oauth_module(Path(config["openclaw_root"])).authorize(
            {"root": DATA, "sender_email": config["expected_sender"], "sender_confirmed": True}, selected)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"oauth_connected": False, "error_type": type(exc).__name__, "sent": 0}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
