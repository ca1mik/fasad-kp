from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from config import Config, ConfigError
from logger import EventLogger
from mailer import Mailer
from models import Lead, SendResult
from sheets import Sheets
from state import StateStore
from workflow import OutreachWorkflow, SafetyError


class SampleSheets:
    def __init__(self, path: Path):
        rows = json.loads(path.read_text(encoding="utf-8"))
        self.leads = [Lead(index + 2, row) for index, row in enumerate(rows)]

    def read_leads(self) -> list[Lead]:
        return list(self.leads)

    def update_lead(self, lead: Lead, updates: dict[str, str]) -> None:
        raise RuntimeError("sample adapter is read-only")

    def healthcheck(self) -> dict[str, str]:
        return {"sample": "ok"}


class SampleMailer:
    def healthcheck(self) -> dict[str, str]:
        return {"sample": "ok"}

    def send(self, lead: Lead, subject: str, body: str, message_id: str) -> SendResult:
        raise RuntimeError("sample adapter never sends")

    def fetch_replies(self, original_ids: set[str]):
        return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Безопасный B2B outreach для мебельной CRM")
    parser.add_argument("--env-file", help="путь к .env", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("healthcheck")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--sample", action="store_true", help="локальная демонстрация без Google и почты")
    sub.add_parser("send-new")
    sub.add_parser("sync-replies")
    sub.add_parser("state-report")
    return parser


def run(argv: list[str] | None = None) -> int:
    # Windows often inherits a legacy console code page; keep Russian previews readable.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    sample = (args.command == "dry-run" and args.sample) or args.command == "state-report"
    try:
        config = Config.from_env(args.env_file, sample=sample)
        if args.command == "send-new" and not config.dry_run:
            config.validate_external()
        state = StateStore(config.state_path)
        logger = EventLogger(config.log_path)
        if args.command == "state-report":
            print(json.dumps(state.report(), ensure_ascii=False, indent=2))
            return 0
        if sample:
            sheets = SampleSheets(Path(__file__).parent / "examples" / "leads.json")
            mailer = SampleMailer()
        else:
            sheets = Sheets(config)
            mailer = Mailer(config)
        workflow = OutreachWorkflow(config, sheets, mailer, state, logger)
        if args.command == "healthcheck":
            result = workflow.healthcheck()
        elif args.command == "dry-run":
            result = workflow.dry_run()
        elif args.command == "send-new":
            result = workflow.send_new()
        elif args.command == "sync-replies":
            result = workflow.sync_replies()
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except (ConfigError, SafetyError) as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
