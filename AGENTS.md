# Agent Instructions

Rules AI agents must follow when working in this repository.

---

## Commit messages

Use **Conventional Commits**.

### Header

* Format: `<type>(optional scope): summary`
* Use lowercase types (`feat`, `fix`, `ci`, `chore`, `docs`)
* Use scopes when relevant
* Write summaries in lowercase, imperative mood

### Body

* Leave a blank line after the header
* Explain **why**, not what
* Use imperative, present tense
* Wrap lines at ~72 characters

The body is optional for trivial changes.

---

## Release tags

* Use the bare version as the tag name — **no `v` prefix** (e.g. `0.1.0a4`, not `v0.1.0a4``)
* Tags must be annotated (`git tag -a`) with a structured release-notes message

---

## Commits

When generating commits via a shell:

* Do **not** pass generated messages directly to `git commit -m`
* Write the commit message to a file or standard input
* Use `git commit -F <file>` or `git commit -F -`
* Disable shell expansion when writing commit messages

This avoids issues with backticks, quotes, and other shell-expanded
characters in generated commit messages.

---

## Code style

Follow existing project conventions.

* Match formatting, naming, and file structure already in use
* Do not reformat unrelated code
* Prefer small, focused changes
* Avoid introducing new patterns without clear benefit

### Language-specific rules

* Respect `.editorconfig` when present
* Do not disable lint rules without justification
* Prefer explicit, readable code over clever abstractions
* Ensure all changes pass `ruff check .`, `ruff format --check .`, `pyright`, and `pytest`

---

## `uv` Workflow Rules

* Use `uv` exclusively for dependency management instead of `pip`
* Always prefix tool and script invocations with `uv run` so they execute inside the managed environment
* Do not manually create, activate, or delete `.venv` directories
* Bump the project version with `uv run python scripts/bump_version.py <new-version>` — it drives `uv version` and propagates the result to `server.json`, which carries the version twice; do **not** edit `pyproject.toml` directly
* Always commit `pyproject.toml`, `uv.lock`, and `server.json` together after a version bump

---

## Attribution

All commits must include an `Assisted-by` trailer line:

```
Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL1] [TOOL2]
```

* **AGENT_NAME** — the AI tool or framework used (e.g. `Claude`, `Cursor`, `Copilot`)
* **MODEL_VERSION** — the specific model version (e.g. `claude-opus-4-6`)
* **[TOOL1] [TOOL2]** — optional, space-separated list of specialized analysis tools used in the change (e.g. `coccinelle`, `sparse`, `smatch`, `clang-tidy`)
* Do **not** list everyday tools like `git`, `gcc`, `make`, or editors

Example:

```
Assisted-by: Claude:claude-opus-4-6 coccinelle sparse
```

---

## MCP Metadata

Normative, high-density metadata: enough for correct tool and parameter selection, minimal to reduce token cost.

### Tools and resources

* Description MUST start with `[Walmart]` and a Verb-Object fragment — `[Walmart] Execute an authenticated API request`, `[Walmart] List OpenAPI operations`. The tag disambiguates in a host's flat, multi-server tool list.
* Describe what changes a caller's decision. Mechanics they cannot influence — retry policy, redirect handling — belong in a module docstring.

### Parameters

* No `[Walmart]` prefix: a parameter is only read inside its own tool's schema.
* Noun phrase, not Verb-Object. Use a verb only for a filter or an action (`Limit to one api`, `Filter by HTTP verb`).
* `Src: <Entity>` for entities this server owns — region/environment/advertiser_id/api/platform → `platforms`, operation id → `operations`.
* Give an example when the shape is not obvious from the name, and keep it current — a stale id steers an agent to build one that cannot resolve.

### Closed value sets

* Values fixed at build time → `Literal`, so the host rejects a bad one before the call.
* Do not enumerate a large set a resource already lists (`api`); use `Src:` instead.
* A `Literal` mirroring a runtime constant needs a test that the two match.

### Annotations

* **Every tool MUST declare `ToolAnnotations`**, mapped from the operation it performs:
  * Read → `read_only_hint=True`
  * Create → `read_only_hint=False`, `destructive_hint=False`, `idempotent_hint=False`
  * Update → `read_only_hint=False`, `destructive_hint=False`, `idempotent_hint=True`
  * Delete → `read_only_hint=False`, `destructive_hint=True`
  * A passthrough tool that can perform any of the above takes the most cautious shape (`destructive_hint=True`, `idempotent_hint=False`)
  * Set `open_world_hint=True` when the tool reaches the network, `False` when it only reads bundled specs or config
  * Omit `destructive_hint`/`idempotent_hint` on read-only tools — they are meaningful only when `read_only_hint=False`
* Writing to the local filesystem is not read-only, even when the network call is a read.
