"""Read-only Gmail history for the exact existing Russian CRM list. No send."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import russia_outreach as ru
from shared_gmail_control import atomic_json, read_control, read_sent

cfg=ru.read_config();bridge=ru.make_bridge(cfg)
with bridge.mailbox_guard(ru.CAMPAIGN):
    results=[ru.recipient_sent_history(bridge,lead) for lead in ru.read_leads()]
    imap=bridge.mailer._open_imap()
    try:cache=read_sent(imap,datetime.now(timezone.utc))
    finally:bridge.mailer._close_imap(imap)
    atomic_json(read_control()['sent_cache'],cache)
    atomic_json(ru.DATA/'gmail-recipient-history-checks.json',results)
    print(json.dumps({'companies_checked':len(results),'prior_matching_offer':sum(r['matching_offer'] for r in results),'any_prior_sent_history':sum(bool(r['sent_matches_found']) for r in results),'sent':0},ensure_ascii=False))
