---
name: excel-model
description: Build an Excel (.xlsx) spreadsheet or financial model with live formulas from a JSON spec. Use whenever a task asks for a spreadsheet, model or forecast.
---

# Excel model

1. Lay the model out as JSON: one or more sheets, each with `rows` (the first row is the header) and optional `formulas` keyed by cell. Use formulas for totals and derived numbers so the model stays live in Excel.
2. Run `make_model.py <spec.json> <artifacts dir>/<file>.xlsx` with the Python, script path and artifacts directory given in your AGENTS.md.
3. Link it in your RESULT comment as `ARTIFACT: xlsx <gateway url>/artifacts/<file>.xlsx <label>`, again using the URL from your AGENTS.md.

The script exits non-zero and prints `spec error: …` if the JSON is malformed. Fix the spec and re-run.

Example spec:

```json
{
  "sheets": [{
    "name": "Lackawanna County",
    "rows": [["Year", "Contract value", "Gross margin", "Gross profit"],
             [2027, 120000, 0.22, null], [2028, 120000, 0.22, null], [2029, 120000, 0.22, null], ["Total"]],
    "formulas": {"D2": "=B2*C2", "D3": "=B3*C3", "D4": "=B4*C4", "B5": "=SUM(B2:B4)", "D5": "=SUM(D2:D4)"}
  }]
}
```
