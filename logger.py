from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


_SECRET_NAMES = re.compile(r"password|secret|token|credential|authorization", re.I)


def _clean(value: Any) -> Any:
    text = str(value or "")
    # Avoid accidental Authorization/password fragments in third-party errors.
    text = re.sub(r"(?i)(bearer|password|token|secret)\s*[:= ]\s*[^\s,;]+", r"\1=***", text)
    return text[:2000]


class EventLogger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, **fields: Any) -> None:
        record: dict[str, Any] = {"timestamp": datetime.now(timezone.utc).isoformat()}
        for key, value in fields.items():
            record[key] = "***" if _SECRET_NAMES.search(key) else _clean(value)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

