"""Role configs: one YAML per employee in backend/roles/ (spec §6.1)."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from company.types import VOICE_TOOL_NAMES

log = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_ROLES_DIR = BACKEND_DIR / "roles"
# Gateway-owned stand-ins, used only until workstream B's backend/roles/ lands.
FIXTURE_ROLES_DIR = BACKEND_DIR / "tests" / "gateway" / "fixtures" / "roles"

REQUIRED_KEYS = (
    "id", "name", "title", "reports_to", "paperclip_agent", "voice",
    "greeting", "persona", "voice_tools", "can_delegate_to",
)


@dataclass
class Role:
    id: str
    name: str
    title: str
    reports_to: str | None
    paperclip_agent: str
    voice: str
    greeting: str
    persona: str
    voice_tools: list[str]
    can_delegate_to: list[str]
    turn_detection: dict | None = None
    sprite: str | None = None
    desk: str | None = None

    def public(self) -> dict:
        """The GET /roles shape (spec §7a)."""
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "reports_to": self.reports_to,
            "voice": self.voice,
            "sprite": self.sprite,
            "desk": self.desk,
        }


def default_roles_dir() -> Path:
    if env := os.getenv("ROLES_DIR"):
        return Path(env)
    if any(DEFAULT_ROLES_DIR.glob("*.yaml")):
        return DEFAULT_ROLES_DIR
    log.warning("backend/roles/ not found; using gateway fixture roles")
    return FIXTURE_ROLES_DIR


def load_roles(roles_dir: Path | None = None) -> dict[str, Role]:
    roles_dir = roles_dir or default_roles_dir()
    roles: dict[str, Role] = {}
    for path in sorted(roles_dir.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        missing = [k for k in REQUIRED_KEYS if k not in raw]
        if missing:
            raise ValueError(f"{path.name}: missing required keys {missing}")
        unknown = [t for t in raw["voice_tools"] if t not in VOICE_TOOL_NAMES]
        if unknown:
            raise ValueError(f"{path.name}: unknown voice tools {unknown}")
        role = Role(
            id=raw["id"],
            name=raw["name"],
            title=raw["title"],
            reports_to=raw["reports_to"],
            paperclip_agent=raw["paperclip_agent"],
            voice=raw["voice"],
            greeting=raw["greeting"],
            persona=raw["persona"],
            voice_tools=list(raw["voice_tools"]),
            can_delegate_to=list(raw["can_delegate_to"] or []),
            turn_detection=raw.get("turn_detection"),
            sprite=raw.get("sprite"),
            desk=raw.get("desk"),
        )
        roles[role.id] = role
    return roles
