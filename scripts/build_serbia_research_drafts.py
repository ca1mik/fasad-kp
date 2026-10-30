"""Prepare research drafts only: no authentication, approval changes, or sending."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serbia_outreach import read_config, read_leads, export_previews  # noqa: E402


def build(root: Path = ROOT) -> dict:
    source = root / "sales/serbia/new-prospects-2026-09-29.csv"
    config = read_config(root / "sales/serbia/campaign.json")
    leads = read_leads(source)
    if any(row["approved"].casefold() != "false" or row["consent_at"] or row["consent_evidence"] for row in leads):
        raise ValueError("Research registry must not imply recipient consent")
    result = export_previews(leads, config, root / "data/serbia-outreach/research-2026-09-29",
                             config["expected_sender"], registry_name=source.relative_to(root).as_posix())
    return {**result, "research_only": True, "approved": 0, "source": str(source)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(build(), ensure_ascii=False, indent=2))
