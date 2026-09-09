# spec-candidates/

Auto-generated **candidate** OpenAPI specs, for reviewing documentation drift.
Nothing here is shipped or loaded at runtime.

Each candidate mirrors the path of the canonical spec it reviews, so the pairing
needs no lookup:

| candidate | canonical |
|---|---|
| `samsclub/ads/sponsored-products.openapi.json` | `src/mcp_walmart_ads/specs/samsclub/ads/sponsored-products.openapi.json` |

Only Sam's Club needs one. Every other bundled spec comes from the ReadMe
api-registry, which serves the document directly — there is nothing to scrape
and nothing to review.

- **Not shipped, never loaded at runtime.** These live outside the package
  (`src/`) on purpose, so they are not bundled into the wheel.
- Candidates are intentionally flat (no `$ref`, no inferred enums/int formats).
  Their only job is to surface **documentation drift** — added, removed, or
  renamed endpoints, parameters, and body fields.
- They are committed deliberately: the committed copy is the baseline a fresh
  scrape is diffed against. Without it in git there would be nothing to compare,
  and drift could not be detected.
- The [`spec drift`](../.github/workflows/spec-drift.yml) workflow regenerates
  them on a schedule and opens a PR on any change. That PR is the human review
  gate: a reviewer ports real changes into the hand-authored canonical spec,
  which is never overwritten automatically.

Regenerate locally, scraping
[developer.samsclub.com](https://developer.samsclub.com/API/overview/) via
[`scripts/build_samsclub_spec.py`](../scripts/build_samsclub_spec.py):

```bash
uv run --group spec-build python scripts/build_samsclub_spec.py
uv run --group spec-build python scripts/build_samsclub_spec.py --check   # exit 1 on drift
```
