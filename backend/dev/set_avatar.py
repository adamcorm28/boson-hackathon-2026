"""Give an employee a lip-synced face from a photo (gateway/avatar.py).

Usage (from backend/):
    .venv/bin/python dev/set_avatar.py ~/Downloads/dwight.jpg                 # role from the file name
    .venv/bin/python dev/set_avatar.py ~/Downloads/friend.png --role engineer

It copies the photo to data/avatars/<role>.<ext> (an earlier photo for that role moves to
data/avatars/old/), takes the role off the Boson live avatar in data/live_avatars.yaml so the photo
is used, and renders the idle loop now (~10 s) so the first call doesn't wait for it.
No gateway restart: refresh the browser tab and call them.

The role comes from --role, or from the file name: a role id (engineer.jpg) or the employee's
first or last name (dwight.jpg, schrute-headshot.png). Roles: ceo (Michael), cfo (Kevin),
eng_lead (Ryan), engineer (Dwight), sales_lead (Jim).

Use your own photo, a teammate who agreed, or drawn art; never an actor's photo (spec §likeness).
"""

import argparse
import asyncio
import re
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from gateway import avatar, live_avatar  # noqa: E402
from gateway.roles import load_roles  # noqa: E402


def _show(path: Path) -> str:
    return str(path.relative_to(BACKEND_DIR)) if path.is_relative_to(BACKEND_DIR) else str(path)


def role_from_name(stem: str, roles) -> str | None:
    words = set(re.split(r"[^a-z0-9]+", stem.lower()))
    if stem.lower() in roles:
        return stem.lower()
    matches = [r.id for r in roles.values() if words & set(r.name.lower().split())]
    return matches[0] if len(matches) == 1 else None


def install_photo(photo: Path, role_id: str) -> Path:
    avatar.AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    for ext in avatar.IMAGE_TYPES:
        old = avatar.AVATARS_DIR / f"{role_id}{ext}"
        if old.exists() and old.resolve() != photo.resolve():
            keep = avatar.AVATARS_DIR / "old" / f"{role_id}-{time.strftime('%Y%m%d-%H%M%S')}{ext}"
            keep.parent.mkdir(exist_ok=True)
            old.rename(keep)
            print(f"  moved the previous photo to {_show(keep)}")
    dest = avatar.AVATARS_DIR / f"{role_id}{photo.suffix.lower()}"
    if photo.resolve() != dest.resolve():
        shutil.copy2(photo, dest)
    dest.touch()  # new mtime: new loop cache and image URL, so nothing stale shows
    return dest


def drop_live_avatar(role_id: str) -> None:
    """Comment the role's line out of live_avatars.yaml: a live avatar would win over the photo."""
    path = live_avatar.AVATARS_FILE
    if not path.exists():
        return
    lines = path.read_text().splitlines(keepends=True)
    out, dropped = [], False
    for line in lines:
        if re.match(rf"\s*{re.escape(role_id)}\s*:", line):
            out.append(f"# {line.rstrip()}  (photo in data/avatars/ instead)\n")
            dropped = True
        else:
            out.append(line)
    if dropped:
        path.write_text("".join(out))
        print(f"  took {role_id} off the live avatar in {_show(path)}")


async def render_loops(role_id: str) -> None:
    kinds = ("idle",) if avatar.sync_mode() else avatar.LOOP_KINDS
    for kind in kinds:
        start = time.monotonic()
        print(f"  rendering the {kind} loop…", end="", flush=True)
        path = await avatar._cached_loop(role_id, kind)
        print(f" done in {time.monotonic() - start:.0f} s ({path.name})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photo", type=Path, help="PNG, JPG or WebP; front-facing head and shoulders works best")
    parser.add_argument("--role", help="ceo, cfo, eng_lead, engineer or sales_lead (default: from the file name)")
    parser.add_argument("--no-render", action="store_true", help="skip pre-rendering; the first call renders instead")
    args = parser.parse_args()

    photo = args.photo.expanduser()
    if not photo.is_file():
        sys.exit(f"No such file: {photo}")
    if photo.suffix.lower() not in avatar.IMAGE_TYPES:
        sys.exit(f"Use a PNG, JPG or WebP photo, not {photo.suffix or 'a file without an extension'}.")
    roles = load_roles()
    role_id = args.role or role_from_name(photo.stem, roles)
    if role_id not in roles:
        sys.exit(f"Which employee? Pass --role with one of: {', '.join(roles)}"
                 + (f" (got {role_id!r})" if role_id else ""))

    print(f"{roles[role_id].name} ({role_id}) ← {photo.name}")
    dest = install_photo(photo, role_id)
    print(f"  photo at {_show(dest)}")
    drop_live_avatar(role_id)
    if not args.no_render:
        asyncio.run(render_loops(role_id))
    print("Done. Refresh the browser tab and call them; no gateway restart needed.")


if __name__ == "__main__":
    main()
