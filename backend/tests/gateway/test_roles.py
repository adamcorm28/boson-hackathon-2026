import textwrap

import pytest

from company.types import ROLE_IDS
from gateway.roles import FIXTURE_ROLES_DIR, load_roles

VALID = textwrap.dedent("""\
    id: eng_lead
    name: Ryan Howard
    title: Engineering Lead (Dunder Mifflin Infinity)
    reports_to: ceo
    paperclip_agent: eng-lead
    voice: default
    greeting: "Yeah, Ryan. Make it quick, I have a pitch."
    persona: |
      You are Ryan.
    turn_detection: {type: server_vad}
    voice_tools: [get_my_work, get_board, get_issue, delegate_task, lookup_company, web_search]
    can_delegate_to: [engineer, eng_lead]
    sprite: ryan
    desk: annex
""")


def write(tmp_path, name, text):
    (tmp_path / f"{name}.yaml").write_text(text)


def test_load_valid_role(tmp_path):
    write(tmp_path, "eng_lead", VALID)
    roles = load_roles(tmp_path)
    r = roles["eng_lead"]
    assert r.name == "Ryan Howard"
    assert r.reports_to == "ceo"
    assert r.voice_tools[-1] == "web_search"
    assert r.can_delegate_to == ["engineer", "eng_lead"]
    assert r.turn_detection == {"type": "server_vad"}
    assert r.desk == "annex"


def test_optional_keys_default_to_none(tmp_path):
    text = "\n".join(l for l in VALID.splitlines() if not l.startswith(("turn_detection", "sprite", "desk")))
    write(tmp_path, "eng_lead", text)
    r = load_roles(tmp_path)["eng_lead"]
    assert r.turn_detection is None and r.sprite is None and r.desk is None


def test_missing_key_raises_with_filename(tmp_path):
    write(tmp_path, "eng_lead", VALID.replace("voice: default\n", ""))
    with pytest.raises(ValueError, match="eng_lead.yaml"):
        load_roles(tmp_path)


def test_unknown_tool_raises(tmp_path):
    write(tmp_path, "eng_lead", VALID.replace("web_search]", "hack_the_pentagon]"))
    with pytest.raises(ValueError, match="hack_the_pentagon"):
        load_roles(tmp_path)


def test_public_shape(tmp_path):
    write(tmp_path, "eng_lead", VALID)
    pub = load_roles(tmp_path)["eng_lead"].public()
    assert set(pub) == {"id", "name", "title", "reports_to", "voice", "sprite", "desk"}
    assert pub["id"] == "eng_lead"


def test_fixture_roles_cover_all_role_ids():
    assert set(load_roles(FIXTURE_ROLES_DIR)) == set(ROLE_IDS)
