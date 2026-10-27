import textwrap

import pytest

from company.types import ROLE_IDS
from gateway.roles import DEFAULT_ROLES_DIR, load_roles

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
    assert set(pub) == {"id", "name", "title", "reports_to", "voice", "sprite", "desk", "responsibilities"}
    assert pub["id"] == "eng_lead"
    assert pub["responsibilities"] == []  # optional key, absent in VALID


def test_responsibilities_load_as_a_list_of_strings(tmp_path):
    write(tmp_path, "eng_lead", VALID + "responsibilities:\n  - Owns Infinity\n  - Triages bugs\n")
    assert load_roles(tmp_path)["eng_lead"].responsibilities == ["Owns Infinity", "Triages bugs"]


def test_responsibilities_must_be_a_list(tmp_path):
    write(tmp_path, "eng_lead", VALID + "responsibilities: Owns Infinity\n")
    with pytest.raises(ValueError, match="responsibilities"):
        load_roles(tmp_path)


def test_every_real_role_lists_responsibilities():
    for role in load_roles(DEFAULT_ROLES_DIR, voice_overrides={}).values():
        assert role.responsibilities and all(isinstance(r, str) and r for r in role.responsibilities), role.id


def test_real_roles_load_and_cover_all_role_ids():
    assert set(load_roles(DEFAULT_ROLES_DIR)) == set(ROLE_IDS)


def test_voice_overrides_replace_role_voice(tmp_path):
    write(tmp_path, "eng_lead", VALID)
    overrides = tmp_path / "voices.yml.txt"  # outside the *.yaml role glob
    overrides.write_text("eng_lead: voice_abc123\nceo: voice_unused\n")
    from gateway.roles import load_voice_overrides
    roles = load_roles(tmp_path, voice_overrides=load_voice_overrides(overrides))
    assert roles["eng_lead"].voice == "voice_abc123"
    assert roles["eng_lead"].preset_voice == "default"  # the fallback if Boson doesn't know the clone
    plain = load_roles(tmp_path, voice_overrides={})["eng_lead"]
    assert plain.voice == "default" and plain.preset_voice is None
    assert load_roles(tmp_path, voice_overrides={})["eng_lead"].voice == "default"


def test_missing_overrides_file_is_fine(tmp_path):
    from gateway.roles import load_voice_overrides
    assert load_voice_overrides(tmp_path / "nope.yaml") == {}
