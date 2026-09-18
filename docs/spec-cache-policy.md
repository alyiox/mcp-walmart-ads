# OpenAPI spec cache policy

**Status:** adopted
**Applies to:** any server whose reads prefer a user-writable cache of OpenAPI documents fetched
from an upstream it does not control

The cache outranks what the package shipped, so whatever a refresh installs is trusted from then
on. This policy bounds what a refresh may do. It fixes rules, not machinery.

---

## 1. Invariant

**A refresh MUST improve a cached document or leave it alone; it MUST NOT degrade one.**

Sections 2-6 are that sentence applied to one path each.

## 2. Trigger

**A refresh MUST NOT be the model's decision.** Staleness is invisible from inside a session -- a
stale document merely lacks an endpoint or names it differently -- so an agent left to judge either
never fires or fires superstitiously after an unrelated failure. The signal is out of band; the
trigger must be too.

Any out-of-band trigger qualifies -- user-invoked tool, schedule, startup check, or several
together -- and each owes section 3 in full and a section 6 report. They are not interchangeable: a
schedule keeps documents current, a tool answers the gap a user hit between two runs. A tool, where
one exists, MUST state its trigger in its description rather than leave the model to infer one.

## 3. Write path

Applies to every install, whatever triggered it: refresh, schedule, or lazy fetch on a miss.

### 3.1 Validate

**Install only a document yielding at least one operation** -- an entry under `paths` keyed by an
HTTP method. This is the trust boundary and the only check worth making, because it tests whether
the server still works after the write. It rejects a `200` carrying an error body, a login page
rendered as JSON, a truncated response, a JSON array. Status and content type do not substitute: a
swagger endpoint behind a gateway answers `200` with something useless more often than `404`.

On failure, keep what is there, report it, continue.

### 3.2 Skip an unchanged write

**Compare the bytes to be written against those on disk; do not write on a match.** Not for
bandwidth: an index keyed on mtime makes a byte-identical rewrite re-parse that document in every
running server, and the usual refresh changes little or nothing. Compare exactly, not by digest --
the bytes are in hand and no digest is recorded.

Serialization MUST be deterministic or the comparison is worthless. Changing its options rewrites
every cached file once: deliberate, not a formatting whim.

### 3.3 Install atomically

**Stage to a temp file, then `os.replace` onto the target. The temp name MUST be unique per
writer** -- pid plus random suffix, or `tempfile.mkstemp` in the target directory. A scratch path
derived from the target alone is shared by every writer, and interleaved writers install a file
that is complete, corrupt, and atomic: worse than a partial one, because nothing downstream detects
it.

A lock is not a substitute -- scratch files are written where no lock is held, by release tooling
for instance, and a lock that degrades silently on a network filesystem must not be the only thing
between two writers. Remove the scratch file on failure.

### 3.4 Bound the whole fetch

**Wrap each document's fetch in one total deadline.** A client timeout applies per socket
operation, so a slow-drip response never trips it and one document can hang far past the configured
value, taking everything queued behind it with it.

### 3.5 Store verbatim, reduce on read

**Write the document as the upstream served it.** Where a server strips weight before handing a
document to a model -- oversized examples, a docs platform's rendering extensions -- that reduction
MUST happen on load. Then a retune needs no re-download, a bug in it cannot reach the cache, and
`unchanged` keeps meaning *upstream did not change* rather than *the parts we kept did not*.

What gets stripped is per-upstream and belongs in the module that strips it.

## 4. Read path

**A cached file that fails to load MUST be deleted, and the read MUST continue as a cache miss.**

* A miss already means something -- shipped copy, or fetch -- so no new recovery path is needed.
* Deleting is what makes it self-correcting. Skipping leaves the file to fail on every later read,
  with its api still advertised (existence checks pass), until someone clears the cache by hand.
* The delete is best effort: a file we cannot remove must still fall through rather than raise.
* Raise only when the miss path also fails -- where a bundle exists, that means the shipped copy is
  damaged too.

**A shipped bundle MUST NOT be written at runtime.** It is the floor that keeps this recovery
available; the worst reachable state is then the version that shipped.

## 5. Concurrency

Writers overlap routinely: two server processes, a server and a release script, a scheduled refresh
and a lazy miss in one process.

* **Fetch outside the lock; lock only to install.** The locked section -- validate, compare, write
  -- is microseconds to milliseconds and never a network call. Nothing may block behind another
  process's download: a stalled tool call is a visible failure, and a scheduled refresh stalling a
  read is worse, since nobody asked for it. Duplicate downloads cost bandwidth, the budget this
  design spends from.
* **On a lazy miss, re-check under the lock** whether the document arrived while fetching, and
  prefer it: a duplicated download becomes a discarded one rather than a redundant write and an
  mtime bump.
* **Use `filelock`**, not a hand-rolled `fcntl`/`msvcrt` shim -- POSIX advisory locks release on
  process death, Windows byte-range locks are mandatory and retry rather than block.
* **Keep the in-process lock as well.** A file lock conflicts between separate file descriptors, so
  it neither replaces nor cooperates with an `asyncio` lock; they cover different races.

Degradation is by design: where locking is unreliable (network filesystems, some container mounts)
the cost is duplicate downloads and a last-writer-wins install of identical content. Correctness
rests on 3.1 and 3.3, not on the lock.

## 6. Reporting

One row per document, `status` exactly one of:

| Status | Meaning |
|---|---|
| `written` | fetched, validated, installed; content differed |
| `unchanged` | fetched, validated; byte-identical to the cached copy |
| `error` | not installed; `error` carries the reason |

* A per-document failure MUST NOT abort the batch.
* Detail belongs in its own field, never folded into the status, so outcomes can be counted without
  parsing prose.
* Rows do not vary by trigger; only their destination does -- the caller, or a log where there is
  none.
* Report what the caller can act on (id, version, operation count), not what they cannot: absolute
  cache paths leak a home directory into an agent's context and inform no decision.

## 7. Variation points

Legitimate differences. Name the answer chosen, so divergence stays deliberate. Sections 1-6 apply
unchanged to every combination.

| Dimension | Alternatives |
|---|---|
| Shipped copy | bundled documents, the floor for a miss; or none, where a miss must fetch |
| Trigger | user-invoked, scheduled, lazy on first use -- any combination |
| Upstream | a registry serving raw URLs; each deployment's own swagger endpoint |
| Operation ids | declared by the document; or synthesized as `METHOD path` |
| Config surface | per-platform credentials; per-platform deployments |

## 8. Out of scope

Excluded deliberately, so they are not re-proposed as oversights:

* **Refresh as a model decision.** Section 2 is the decision, not an omission.
* **When a scheduled refresh runs**, and the machinery that takes -- interval, lease, shared state,
  backoff. This policy bounds what a refresh does, not how often.
* **Conditional requests.** `ETag`/`If-Modified-Since` optimise a cost that does not matter at this
  cadence and add a trust assumption that does: a false `304` silently misses an update, and these
  documents sit behind CDNs whose validators describe the edge node.
* **A shared library.** The policy travels; each implementation is small enough to live in the
  module that already owns the concern.
* **Normalising a document before comparing it.** If an upstream stamps a generated timestamp into
  its output, every refresh rewrites the file. Fix it then, if it shows up.

Assisted-by: Claude:claude-opus-5
