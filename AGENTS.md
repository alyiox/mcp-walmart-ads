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
* Use `uv version <new-version>` to bump the project version — do **not** edit `pyproject.toml` directly
* Always commit both `pyproject.toml` and `uv.lock` together after a version bump

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

* **The tool/parameter description MUST start with [ClickHouse], followed by a Verb-Object fragment**, e.g. `[ClickHouse] Execute read-only SQL`, `[ClickHouse] List databases`, `[ClickHouse] Describe table`.
* **Use tag-based lineage (Src: <Entity>) for parameters that refer to ClickHouse entities** (e.g. database name → Src: databases, table name → Src: tables).

