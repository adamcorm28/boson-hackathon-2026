"""Register a teammate's recorded voice as a reusable Boson voice (spec §likeness: teammate clones only).

    .venv/bin/python spikes/clone_voice.py data/voices/michael-scott.mp3 --description "Michael (teammate impression)"
    .venv/bin/python spikes/clone_voice.py data/voices/x.mp3 --text "exact words spoken in the clip"

Without --text, the clip is transcribed with higgs-stt-3.1 first. Prints the `voice_<id>` to put
in the role YAML's `voice:` field. Re-running on the same audio returns the same id.
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API = "https://api.boson.ai/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['BOSON_API_KEY']}"}


def transcribe(path: Path) -> str:
    with path.open("rb") as f:
        r = httpx.post(f"{API}/audio/transcriptions", headers=HEADERS, timeout=60,
                       files={"file": (path.name, f, "audio/mpeg")}, data={"model": "higgs-stt-3.1"})
    if r.status_code != 200:
        sys.exit(f"transcription failed ({r.status_code}): {r.text}\nPass --text with the clip's words instead.")
    return r.json()["text"].strip()


def create_voice(path: Path, text: str, description: str | None) -> dict:
    data = {"ref_text": text} | ({"description": description} if description else {})
    with path.open("rb") as f:
        r = httpx.post(f"{API}/audio/voices", headers=HEADERS, timeout=60,
                       files={"ref_audio": (path.name, f, "audio/mpeg")}, data=data)
    if r.status_code != 200:
        sys.exit(f"voice creation failed ({r.status_code}): {r.text}")
    return r.json()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("audio", type=Path)
    p.add_argument("--text", help="exact transcript of the clip (skips STT)")
    p.add_argument("--description")
    args = p.parse_args()

    text = args.text or transcribe(args.audio)
    print(f"ref_text: {text}")
    voice = create_voice(args.audio, text, args.description)
    print(f"voice: {voice.get('voice_id') or voice['voice']}")  # live API says voice_id; docs say voice


if __name__ == "__main__":
    main()
