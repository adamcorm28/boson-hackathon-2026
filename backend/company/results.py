"""Parse the RESULT convention work-body agents use to report finished voice tasks.

    RESULT: <2–4 sentence summary>
    ARTIFACT: <kind> <url> <label>      # zero or more lines
"""

from pathlib import Path

from company.types import Artifact, Comment

ARTIFACT_KINDS = ("pr", "diff", "pptx", "xlsx", "link")


def parse_result(comments: list[Comment]) -> tuple[str, list[Artifact]] | None:
    """(summary, artifacts) from the last comment that starts with RESULT:, or None if there isn't one.

    The summary runs from RESULT: to the first ARTIFACT: line or blank line, since agents sometimes
    append extra content after their result. Artifact lines with an unknown kind or missing fields are skipped.
    """
    body = next((c.body.strip() for c in reversed(comments) if c.body.lstrip().startswith("RESULT:")), None)
    if body is None:
        return None
    lines = body[len("RESULT:"):].splitlines()
    summary: list[str] = []
    for line in lines:
        if not line.strip() or line.startswith("ARTIFACT:"):
            break
        summary.append(line.strip())
    artifacts = []
    for line in lines:
        if line.startswith("ARTIFACT:"):
            parts = line[len("ARTIFACT:"):].split(maxsplit=2)
            if len(parts) == 3 and parts[0] in ARTIFACT_KINDS:
                artifacts.append(Artifact(kind=parts[0], url=parts[1], label=parts[2].strip()))
    return " ".join(summary), artifacts


BRIEF_MAX_CHARS = 4000


def read_brief(artifacts: list[Artifact], artifacts_dir: Path) -> str | None:
    """Text of the first linked Markdown artifact that exists locally (e.g. a research brief), truncated."""
    for artifact in artifacts:
        name = artifact.url.rsplit("/artifacts/", 1)[-1] if "/artifacts/" in artifact.url else None
        if artifact.kind == "link" and name and name.endswith(".md") and "/" not in name:
            path = Path(artifacts_dir) / name
            if path.is_file():
                return path.read_text()[:BRIEF_MAX_CHARS]
    return None
