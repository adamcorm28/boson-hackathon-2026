"""Lazy access to workstream B modules that may not have landed yet.

The gateway only reaches `company.data_tools`, `company.results` and
`company.watcher` through here. Until B pushes them, small fallbacks keep the
gateway working against the mock; once they exist, B's versions win with no
gateway change. Delete the fallbacks after integration.
"""

import importlib
import logging
from types import SimpleNamespace

from company.types import Artifact, Comment

log = logging.getLogger(__name__)

ARTIFACT_KINDS = ("pr", "diff", "pptx", "xlsx", "pdf", "link")


def _optional(module: str):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise  # B's module exists but is broken: surface it
        return None


# --- data_tools ------------------------------------------------------------------------

_FALLBACK_DEALS = [
    {"account": "Lackawanna County Schools", "value_per_year": 120000, "stage": "quote sent",
     "owner": "sales_lead", "blocker": "Infinity checkout not applying the bulk discount"},
    {"account": "Blue Cross of Pennsylvania", "value_per_year": 64000, "stage": "negotiation",
     "owner": "sales_lead", "blocker": None},
]
_FALLBACK_INBOX = [
    {"id": "e1", "from": "David Wallace", "subject": "Q4 numbers", "unread": True,
     "snippet": "Michael, I need the Scranton Q4 numbers by Monday.",
     "body": "Michael, I need the Scranton Q4 numbers by Monday: sales, margin and forecast vs. Stamford. Thanks, David."},
]


def _fallback_data_tools() -> SimpleNamespace:
    def find(items, key, value):
        return next((i for i in items if value.lower() in i[key].lower()), None)

    return SimpleNamespace(
        company_overview=lambda: {
            "branch": "Dunder Mifflin Scranton", "monthly_sales": 700000, "gross_margin": 0.22,
            "q4_goal": "Beat the Stamford branch", "q4_progress_pct": 61, "headline_kpis": {},
        },
        get_pipeline=lambda: list(_FALLBACK_DEALS),
        get_deal=lambda name: find(_FALLBACK_DEALS, "account", name),
        get_financials=lambda: {"monthly_sales": 700000, "gross_margin": 0.22, "months": []},
        read_inbox=lambda: [{k: v for k, v in e.items() if k != "body"} for e in _FALLBACK_INBOX],
        read_email=lambda email_id: next((e for e in _FALLBACK_INBOX if e["id"] == email_id), None),
        lookup_company=lambda topic: {"topic": topic, "matches": (
            [{"section": "Pricing", "text": "Bulk discount: 10% off orders of 50+ cases."}]
            if "discount" in topic.lower() else [])},
    )


def data_tools():
    return _optional("company.data_tools") or _fallback_data_tools()


# --- results ---------------------------------------------------------------------------


def _fallback_parse_result(comments: list[Comment]) -> tuple[str, list[Artifact]] | None:
    """Same contract as B8's company.results.parse_result."""
    body = next((c.body for c in reversed(comments) if c.body.startswith("RESULT:")), None)
    if body is None:
        return None
    summary_lines, artifacts = [], []
    in_summary = True
    for i, line in enumerate(body.splitlines()):
        if line.startswith("ARTIFACT:"):
            in_summary = False
            parts = line[len("ARTIFACT:"):].split(maxsplit=2)
            if len(parts) == 3 and parts[0] in ARTIFACT_KINDS:
                artifacts.append(Artifact(kind=parts[0], url=parts[1], label=parts[2]))
        elif in_summary:
            summary_lines.append(line[len("RESULT:"):] if i == 0 else line)
    return " ".join(l.strip() for l in summary_lines if l.strip()), artifacts


def parse_result(comments: list[Comment]) -> tuple[str, list[Artifact]] | None:
    results = _optional("company.results")
    return results.parse_result(comments) if results else _fallback_parse_result(comments)


# --- watcher ---------------------------------------------------------------------------


def make_watcher(company, on_update, on_complete, interval: float = 3.0):
    """B9's TaskWatcher, or None until it lands."""
    watcher = _optional("company.watcher")
    if watcher is None:
        log.warning("company.watcher not available yet; completions won't be announced")
        return None
    return watcher.TaskWatcher(company, on_update, on_complete, interval=interval)
