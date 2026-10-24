from pathlib import Path

import pytest
import yaml

from company.types import ROLE_IDS, VOICE_TOOL_NAMES
from gateway.roles import load_roles

ROLES_DIR = Path(__file__).parent.parent.parent / "roles"
REQUIRED = {"id", "name", "title", "reports_to", "paperclip_agent", "voice", "greeting", "persona",
            "voice_tools", "can_delegate_to"}
PERSONA_RULES = (
    "excellent at your job",
    "Lead with the answer",
    "never refuse, stall, hold back information, or let banter get in the way of the work",
    "at most one comedy bit",
    "Every number and fact comes from your tools",
    "Short spoken sentences",
)


@pytest.fixture(scope="module")
def raw():
    return {p.stem: yaml.safe_load(p.read_text()) for p in ROLES_DIR.glob("*.yaml")}


def test_all_roles_present(raw):
    assert set(raw) == set(ROLE_IDS)


def test_required_keys_and_id_matches_filename(raw):
    for stem, role in raw.items():
        assert REQUIRED <= set(role), stem
        assert role["id"] == stem


def test_voice_tools_known_and_max_six(raw):
    for stem, role in raw.items():
        assert set(role["voice_tools"]) <= VOICE_TOOL_NAMES, stem
        assert len(role["voice_tools"]) <= 6, stem


def test_reports_to_tree(raw):
    assert raw["ceo"]["reports_to"] is None
    assert raw["engineer"]["reports_to"] == "eng_lead"
    for r in ("cfo", "eng_lead", "sales_lead"):
        assert raw[r]["reports_to"] == "ceo"


def test_delegation_targets_are_roles(raw):
    for stem, role in raw.items():
        assert set(role["can_delegate_to"] or []) <= set(ROLE_IDS), stem
    assert set(raw["ceo"]["can_delegate_to"]) == set(ROLE_IDS)
    assert "engineer" in raw["eng_lead"]["can_delegate_to"]


def test_every_role_can_take_work_directly(raw):
    for stem, role in raw.items():
        assert stem in role["can_delegate_to"], stem
        assert "delegate_task" in role["voice_tools"], stem


DYSFUNCTION = ("resent", "suspicious", "distracted", "scared", "avoid", "defensive", "contempt", "beneath")


def test_personas_have_no_dysfunctional_traits(raw):
    for stem, role in raw.items():
        persona = role["persona"].lower()
        assert not [w for w in DYSFUNCTION if w in persona], stem


def test_delegate_tool_matches_delegation_targets(raw):
    for stem, role in raw.items():
        assert ("delegate_task" in role["voice_tools"]) == bool(role["can_delegate_to"]), stem


def test_voices_and_desks(raw):
    assert {r: raw[r]["voice"] for r in raw} == {
        "ceo": "marcus", "cfo": "default", "eng_lead": "default", "engineer": "jake", "sales_lead": "oliver"}
    assert {r: raw[r]["desk"] for r in raw} == {
        "ceo": "michael_office", "cfo": "accounting", "eng_lead": "annex",
        "engineer": "dwight_desk", "sales_lead": "jim_desk"}


def test_persona_has_rules(raw):
    for stem, role in raw.items():
        for rule in PERSONA_RULES:
            assert rule in role["persona"], (stem, rule)


def test_gateway_loader_accepts_roles():
    roles = load_roles(ROLES_DIR)
    assert roles["ceo"].name == "Michael Scott"
    assert roles["sales_lead"].public()["desk"] == "jim_desk"
