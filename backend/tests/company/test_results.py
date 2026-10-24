from company.results import parse_result
from company.types import Artifact, Comment


def c(body: str) -> Comment:
    return Comment(author_role="engineer", body=body, created_at="2026-10-24T05:00:00Z")


def test_parse_result_summary_and_artifacts():
    assert parse_result([c("RESULT: Fixed it.\nARTIFACT: diff http://x/a.diff The fix")]) == (
        "Fixed it.", [Artifact("diff", "http://x/a.diff", "The fix")])


def test_parse_result_none_without_marker():
    assert parse_result([c("Working on it."), c("Ryan Howard: RESULT: not at the start")]) is None


def test_parse_result_skips_bad_artifact_lines():
    summary, artifacts = parse_result([c(
        "RESULT: Done.\nARTIFACT: video http://x/v.mp4 Unknown kind\nARTIFACT: pptx\n"
        "ARTIFACT: pptx http://x/deck.pptx Prospect deck")])
    assert artifacts == [Artifact("pptx", "http://x/deck.pptx", "Prospect deck")]


def test_parse_result_uses_last_result_comment():
    summary, _ = parse_result([c("RESULT: First try."), c("Follow-up."), c("RESULT: Second try.")])
    assert summary == "Second try."


def test_parse_result_multiline_summary_stops_at_trailing_content():
    # Seen in the Paperclip spike: agents may append extra content after the ARTIFACT lines.
    summary, artifacts = parse_result([c(
        "RESULT: Wrote the haiku.\nIt is 5-7-5.\nARTIFACT: link https://example.com Example\n\n> Blank sheet holds the dawn")])
    assert summary == "Wrote the haiku. It is 5-7-5."
    assert len(artifacts) == 1


def test_parse_result_tolerates_leading_whitespace():
    assert parse_result([c("\n  RESULT: Done.")]) == ("Done.", [])


def test_read_brief_reads_linked_markdown_artifact(tmp_path):
    from company.results import read_brief
    (tmp_path / "finance-tools.md").write_text("# Findings\n" + "x" * 5000)
    artifacts = [Artifact("link", "http://localhost:8000/artifacts/finance-tools.md", "Brief"),
                 Artifact("pptx", "http://localhost:8000/artifacts/deck.pptx", "Deck")]
    text = read_brief(artifacts, tmp_path)
    assert text.startswith("# Findings") and len(text) <= 4000


def test_read_brief_none_without_markdown(tmp_path):
    from company.results import read_brief
    assert read_brief([Artifact("diff", "http://x/artifacts/a.diff", "d")], tmp_path) is None
    assert read_brief([Artifact("link", "http://x/artifacts/missing.md", "m")], tmp_path) is None
