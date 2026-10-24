"""Role configs: one YAML per employee in backend/roles/ (spec §6.1)."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from company.types import VOICE_TOOL_NAMES

BACKEND_DIR = Path(__file__).parent.parent
DEFAULT_ROLES_DIR = BACKEND_DIR / "roles"
# Per-machine voice choices ({role_id: voice}), e.g. teammates' cloned voices, which belong to
# one Boson account. backend/data/ is gitignored, so this never changes the shared role files.
DEFAULT_VOICE_OVERRIDES = BACKEND_DIR / "data" / "voice_overrides.yaml"

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
    return Path(os.getenv("ROLES_DIR", DEFAULT_ROLES_DIR))


def load_voice_overrides(path: Path | None = None) -> dict[str, str]:
    path = Path(path or os.getenv("VOICE_OVERRIDES", DEFAULT_VOICE_OVERRIDES))
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    return {str(k): str(v) for k, v in raw.items() if v}


def load_roles(roles_dir: Path | None = None, voice_overrides: dict[str, str] | None = None) -> dict[str, Role]:
    roles_dir = roles_dir or default_roles_dir()
    voices = load_voice_overrides() if voice_overrides is None else voice_overrides
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
            voice=voices.get(raw["id"], raw["voice"]),
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
