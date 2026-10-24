---
name: pdf-report
description: Turn a Markdown brief or report into a PDF the user can read. Use when a task asks for a document, report, write-up or PDF.
---

# PDF report

1. Write the content as Markdown: a `#` title, then `##` sections, short paragraphs, bullet lists and links to sources.
2. Run `make_pdf.py <brief.md> <artifacts dir>/<file>.pdf`, with the Python, script path and artifacts directory given in your AGENTS.md. The title comes from the first `#` heading, or pass `--title "…"`.
3. Link it in your RESULT comment as `ARTIFACT: pdf <gateway url>/artifacts/<file>.pdf <label>`, using the URL from your AGENTS.md.

The script exits non-zero with `error: …` if the source file is missing.
