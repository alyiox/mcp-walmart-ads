# spec-candidate/

Auto-generated **candidate** OpenAPI spec, scraped from the
[developer.samsclub.com](https://developer.samsclub.com/API/overview/) docs by
[`scripts/build_samsclub_spec.py`](../scripts/build_samsclub_spec.py).

- **Not shipped and never loaded at runtime.** It lives outside the package
  (`src/`) on purpose, so it is not bundled into the wheel.
- It is intentionally flat (no `$ref`, no inferred enums/int formats). Its only
  job is to surface **documentation drift** — added/removed/renamed endpoints,
  parameters, and body fields.
- The [`Spec drift`](../.github/workflows/spec-drift.yml) workflow regenerates it
  on a schedule and opens a PR when it changes. That PR is the human review gate:
  a reviewer ports real changes into the hand-authored canonical spec at
  `src/mcp_walmart_ads/specs/samsclub/sponsored.openapi.json`, which is
  never overwritten automatically.

Regenerate locally:

```bash
uv run --group spec-build python scripts/build_samsclub_spec.py
uv run --group spec-build python scripts/build_samsclub_spec.py --check   # exit 1 on drift
```
