"""Bump the project version in every file that carries it.

Run from the repo root::

    uv run python scripts/bump_version.py 0.2.1          # set an exact version
    uv run python scripts/bump_version.py --bump patch   # 0.2.0 -> 0.2.1
    uv run python scripts/bump_version.py --bump alpha   # 0.2.0 -> 0.2.1a1
    uv run python scripts/bump_version.py --dry-run 0.3.0
    uv run python scripts/bump_version.py                # no bump: sync only

Arguments are handed to ``uv version`` unchanged, so uv keeps ownership of the
PEP 440 arithmetic, ``pyproject.toml``, and the ``uv.lock`` update -- this
script only propagates the result to ``server.json``, the one versioned file uv
knows nothing about. It carries the version twice, at the top level and in the
pypi package entry, and both must move together.

``server.json`` is set to whatever ``pyproject.toml`` ends up at rather than
bumped on its own, so running with no arguments repairs drift between the two
instead of doubling it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_JSON = ROOT / "server.json"


def uv_version(argv: list[str]) -> str:
    """Run ``uv version`` with ``argv`` and return the resulting version."""
    result = subprocess.run(
        ["uv", "version", "--short", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode or 1)
    version = result.stdout.strip()
    if not version or "\n" in version:
        # `--help`, or any future flag that makes uv print prose instead of a
        # version. Hand it back verbatim rather than writing it to a file.
        sys.stdout.write(result.stdout)
        raise SystemExit(0 if version else 1)
    return version


def sync_server_json(version: str, *, write: bool) -> list[str]:
    """Point every version field in ``server.json`` at ``version``.

    Returns one line per field that was stale, empty when nothing moved. The
    file is re-serialized rather than patched in place, which is what the
    publish workflow already does to it with jq at tag time, so both agree on
    the formatting.
    """
    data = json.loads(SERVER_JSON.read_text(encoding="utf-8"))

    changed: list[str] = []
    if data.get("version") != version:
        changed.append(f"version: {data.get('version')} -> {version}")
        data["version"] = version
    for index, package in enumerate(data.get("packages") or []):
        if package.get("version") != version:
            changed.append(f"packages[{index}].version: {package.get('version')} -> {version}")
            package["version"] = version

    if changed and write:
        SERVER_JSON.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    version = uv_version(argv)
    changed = sync_server_json(version, write=not dry_run)

    print(f"version {version}")
    for line in changed:
        print(f"  server.json  {line}")
    if not changed:
        print("  server.json  already in step")

    if dry_run:
        print("\n--dry-run: nothing written")
        return 0

    print("\nStage pyproject.toml, uv.lock and server.json together.")
    print(f"Tag the release commit {version} -- annotated, no 'v' prefix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
