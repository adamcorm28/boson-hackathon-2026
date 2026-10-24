---
name: pitch-deck
description: Build a PowerPoint (.pptx) pitch deck from a JSON outline. Use whenever a task asks for a deck, slides or a presentation.
---

# Pitch deck

1. Write the outline as JSON: a cover title and subtitle, then 4–5 content slides with 3–5 short bullets each.
2. Run `make_deck.py <spec.json> <artifacts dir>/<file>.pptx` with the Python, script path and artifacts directory given in your AGENTS.md.
3. Link it in your RESULT comment as `ARTIFACT: pptx <gateway url>/artifacts/<file>.pptx <label>`, again using the URL from your AGENTS.md.

The script exits non-zero and prints `spec error: …` if the JSON is malformed. Fix the spec and re-run.

Example spec:

```json
{
  "title": "Five Scranton-Area Prospects",
  "subtitle": "Dunder Mifflin Scranton · Q4",
  "slides": [
    {"title": "Why Dunder Mifflin", "bullets": ["Local delivery in 24 hours", "10% off orders of 50+ cases", "One rep who knows your account"]},
    {"title": "Keystone Community College", "bullets": ["Three campuses, one supplier", "Est. $42k/yr", "Next step: campus facilities meeting"]}
  ]
}
```
