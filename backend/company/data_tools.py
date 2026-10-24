"""Read-only views of the seeded Dunder Mifflin data, for the voice tools.

Pure functions returning JSON-safe dicts and lists. The data files are loaded
once at import; edit backend/company/data/* to change the story.
"""

import copy
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CLOSED_STAGES = ("closed_won", "closed_lost")
MAX_MATCHES = 3
MAX_MATCH_CHARS = 600
_STOPWORDS = {"the", "and", "our", "for", "what", "about", "with", "how", "does", "are", "you", "who", "this",
              "is", "on", "in", "of", "to", "we", "do", "it", "an", "at", "me"}


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text())


def _sections(markdown: str) -> list[tuple[str, str]]:
    """(heading, body) for each `## ` section."""
    parts = re.split(r"^## +(.+)$", markdown, flags=re.MULTILINE)
    return [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


_KPIS = _load("kpis.json")
_FINANCIALS = _load("financials.json")
_CRM = _load("crm.json")
_INBOX = _load("inbox.json")
_HANDBOOK = _sections((DATA_DIR / "handbook.md").read_text())


def company_overview() -> dict:
    open_pipeline = sum(d["value_per_year"] for d in _CRM if d["stage"] not in CLOSED_STAGES)
    return {
        "branch": _KPIS["branch"],
        "as_of": _KPIS["as_of"],
        "monthly_sales": _KPIS["monthly_sales"],
        "gross_margin": _KPIS["gross_margin"],
        "q4_goal": _KPIS["q4_goal"],
        "q4_target_sales": _KPIS["q4_target_sales"],
        "q4_sales_to_date": _KPIS["q4_sales_to_date"],
        "stamford_q4_sales_to_date": _KPIS["stamford_q4_sales_to_date"],
        "q4_progress_pct": round(100 * _KPIS["q4_sales_to_date"] / _KPIS["q4_target_sales"]),
        "headline_kpis": {**_KPIS["headline_kpis"], "open_pipeline_value_per_year": open_pipeline},
    }


def get_pipeline() -> list[dict]:
    return copy.deepcopy(_CRM)


def get_deal(name: str) -> dict | None:
    needle = name.lower().strip()
    return copy.deepcopy(next((d for d in _CRM if needle and needle in d["account"].lower()), None))


def get_financials() -> dict:
    months = copy.deepcopy(_FINANCIALS["months"])
    latest = months[-1]
    return {
        "currency": _FINANCIALS["currency"],
        "monthly_sales": latest["sales"],
        "gross_margin": latest["gross_margin"],
        "net_income_last_month": latest["net_income"],
        "trailing_12m_sales": sum(m["sales"] for m in months),
        "months": months,
    }


def read_inbox() -> list[dict]:
    return [
        {"id": e["id"], "from": e["from"], "subject": e["subject"], "snippet": e["body"][:120], "unread": e["unread"]}
        for e in _INBOX
    ]


def read_email(email_id: str) -> dict | None:
    email = next((e for e in _INBOX if e["id"] == email_id), None)
    if email is None:
        return None
    return {**read_inbox()[_INBOX.index(email)], "body": email["body"]}


def lookup_company(topic: str) -> dict:
    """Rank handbook sections by how many topic words they contain (heading words and the exact phrase count extra)."""
    phrase = topic.lower().strip()
    words = {w for w in re.findall(r"[a-z0-9%$]+", phrase) if len(w) >= 2 and w not in _STOPWORDS}
    scored = []
    for heading, body in _HANDBOOK:
        h, b = heading.lower(), body.lower()
        score = sum(1 for w in words if w in h or w in b) + sum(1 for w in words if w in h)
        if score and phrase in h + "\n" + b:
            score += 2
        if score:
            scored.append((score, heading, body))
    scored.sort(key=lambda s: -s[0])  # stable: ties keep handbook order
    return {
        "topic": topic,
        "matches": [{"section": h, "text": b[:MAX_MATCH_CHARS]} for _, h, b in scored[:MAX_MATCHES]],
    }
