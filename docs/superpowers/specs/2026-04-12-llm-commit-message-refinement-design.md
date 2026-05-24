# LLM-Refined Commit Messages for Snapshot Repos

**Status:** Draft
**Date:** 2026-04-12
**Related:** `docs/VECTOR-DB-DESIGN.md`, `docs/VOCABULARY.md`, `src/repogerbil/core/snapshot.py`

> Historical design note. This file records the April 2026 design exploration and is not the current user-facing reference. The implemented default Ollama model is configured in `Settings.llm_model` (`qwen3-coder-next:q8_0` at the time this note was updated), and the current CLI/docs are authoritative.

---

## Context

The `gerbil snapshot` command collects commits from one or more source repos, deduplicates by tree state, groups by cadence, and writes one commit per group into a destination repo. The commit messages it writes today come from `_build_snapshot_message()` in `snapshot.py`, which parses conventional-commit prefixes from source commit subjects and produces output like:

```
2026-04-07: 3 commits

- feat: add a
- fix: add b
- chore: update
```

This is low signal. Source subjects are often inaccurate, missing, or written in styles the regex doesn't recognize. The resulting history reads like a spreadsheet of someone else's commits rather than a coherent narrative.

This spec replaces that parsing approach with an LLM-generated narrative per snapshot commit, grounded in:

1. The **actual files** each group touched (not the subjects their authors wrote)
2. A **vector database** of similar prior groups' file signatures and refined messages
3. The project's **existing vocabulary** (`instantiate`, `interface`, `remediate`, `harden`, `decouple`, `qualify`, `streamline`, `specify`, `baseline`, `deprecate`) as a hard constraint on the output verb

The LLM runs locally on Ollama (Gemma 4). Output is JSON-schema-constrained. Generated messages are cached, deterministic, and optionally reviewed/edited by the user before application.

---

## Non-Goals

- **No attribution in commit messages.** No `Refined-By` trailers, no co-author lines, no markers that identify the LLM as the message source. Full provenance lives in a side-table in the DB. Trailers may be added later.
- **No cloud LLM calls.** Ollama is the only inference target for v1. Claude API integration is out of scope.
- **No rewriting of user working repos.** Refinement only operates on snapshot-created repos (detected by a marker file). Users' real git history is never rewritten.
- **No automatic changelog generation** beyond per-commit messages. Project-level changelog synthesis is a separate feature.

---

## High-Level Flow

```
source repo(s)
     │
     ▼
 gerbil snapshot  ────► snapshot repo (commits have provisional messages)
     │
     ▼
 gerbil refine   ────► vector DB query + Gemma 4 via Ollama + vocab validation
     │                       │
     │                       ▼
     │                 changelog.yaml  (reviewable artifact — Q11)
     │                       │
     ▼                       ▼
 refined snapshot repo (commits rebuilt with LLM-generated messages)
     │
     └────► side-table DB record per commit
            (prompt, retrieved context, model, cache key, timestamp)
```

Refinement runs in three modes, all backed by the same core library:

1. **Inline**: `gerbil snapshot --llm-refine` — refinement happens during snapshot creation, message applied to the first-built commit.
2. **Post-pass**: `gerbil refine <repo>` — rewrites messages on an already-built snapshot repo using `commit-tree` in place.
3. **On-demand via MCP**: Claude Code / Codex call `refine_snapshot` or `preview_refinement` tools.

---

## Architecture

### Layer 1 — Data Collection (extension of existing code)

For each `TimeGroup`, collect the union of files touched across all its commits. The existing `CommitInfo.files` field already carries per-commit file lists when `include_files=True` is passed to `get_commits_for_date()` / `get_commits_for_path()`. Snapshot-time refinement calls these with `include_files=True`; post-pass refinement re-derives file lists from the snapshot repo itself.

The **group signature** is the sorted list of files changed plus a normalized subsystem-token list (see Layer 3).

### Layer 2 — Vector DB (extension of existing `vectordb.py`)

New ChromaDB collection: **`groups`**

```
{
  id: "<snapshot-repo-id>/<group-date>/<group-index>",
  embedding: embed(file_signature + subsystem_tokens),
  metadata: {
    snapshot_id: str,
    date: str,
    commit_sha: str,              # filled in after commit-tree
    file_count: int,
    subsystem_labels: [str],      # resolved scopes
    vocab_verb: str,              # the chosen category (validated)
    refined_message: str,         # full multi-line refined message
    original_subjects: [str],     # source commit subjects (for audit)
    model_version: str,
    prompt_version: str,
    vocab_version: str,
    refined_at: iso-datetime,
  }
}
```

Persistence scope: **project-local**, default path `<snapshot-repo>/.repogerbil/vectordb/`. Travels with the snapshot repo. Re-runs reuse accumulated context.

Existing `changelogs` / `changes` / `filepaths` / `diffs` collections are unchanged; the `groups` collection is additive.

### Layer 3 — Scope Resolution

Maps file paths → subsystem labels (the `scope` in `instantiate(scope)`).

Hybrid resolver (Q2-D):

1. **Config-first**: `.repogerbil.toml` `[scopes]` section with path globs → label strings.
2. **DB-grounded fallback**: for unmapped paths, query the `groups` collection for the closest prior group that touched similar paths; use its `subsystem_labels` as candidates.
3. **LLM final fallback**: if (1) and (2) produce nothing, the LLM is asked to propose a scope label from the file list, constrained by the JSON schema.

Resolved labels flow into both the embedding input (improves retrieval) and the prompt (gives the LLM its scope choice).

### Layer 4 — LLM Client (new)

Module: `src/repogerbil/llm/ollama.py`

```python
class OllamaClient(Protocol):
    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]: ...
```

Implementations:
- `HTTPOllamaClient` — real client targeting `http://localhost:11434`. Excluded from unit coverage (transport boundary, per Q10-D).
- `FakeOllamaClient` — deterministic fixture-driven client for tests. Returns fixture responses keyed by input hash.

Structured output (Q1-B) is enforced via Ollama's `format: <json-schema>` option:

```json
{
  "type": "object",
  "required": ["entries", "summary"],
  "properties": {
    "entries": {
      "type": "array",
      "minItems": 1,
      "maxItems": 4,
      "items": {
        "type": "object",
        "required": ["verb", "scope", "description"],
        "properties": {
          "verb": {
            "type": "string",
            "enum": ["instantiate", "interface", "remediate", "harden",
                     "margin", "decouple", "qualify", "streamline",
                     "specify", "baseline", "deprecate"]
          },
          "scope": {"type": "string", "minLength": 1, "maxLength": 40},
          "description": {"type": "string", "minLength": 5, "maxLength": 120}
        }
      }
    },
    "summary": {"type": "string", "minLength": 20, "maxLength": 600}
  }
}
```

The commit message is composed from this structured output:
- Each `entries[i]` becomes one line: `{verb}({scope}): {description}`
- Then blank line, then `summary` as the body

### Layer 5 — Prompt

Module: `src/repogerbil/llm/prompt.py`

The prompt assembles:
1. System role: "You refine commit messages for a reconstructed git history."
2. Vocabulary block: enumerated verbs with one-line usage hints (from `vocabulary.py`).
3. Scope guidance: the file→subsystem mappings relevant to this group.
4. Retrieved examples: top-K (default 5) similar prior groups, shown as `(file list) → (refined message)`.
5. Bootstrap examples (Q3-D): seeded curated pairs included when the DB is empty or has fewer than N prior groups.
6. This group: file list, original subjects, commit count, date.
7. Output instruction: "Produce JSON matching the schema. Multiple `entries` only when the files span genuinely distinct concerns."

The prompt template is **versioned** — version string goes into the cache key.

### Layer 6 — Cache

Module: `src/repogerbil/llm/cache.py`

Content-addressed, stored at `<snapshot-repo>/.repogerbil/llm-cache/` (Q4-C).

Cache key:
```
sha256(
  vocab_version
  + prompt_template_version
  + scope_taxonomy_version
  + sorted(file_signature)
  + sorted(retrieved_context_ids)
  + model_name
)
```

Value: the LLM JSON response. On hit, skip Ollama entirely. Override via `--no-cache` or `--force`.

Cache is also the idempotency gate (Q7-D). Running `gerbil refine` twice is effectively a no-op unless one of the cache-key inputs changed.

### Versioning

Three version strings participate in the cache key:

| Version | Lives in | Bumped when |
|---|---|---|
| `VOCAB_VERSION` | `src/repogerbil/core/vocabulary.py` | categories or verbs change |
| `PROMPT_VERSION` | `src/repogerbil/llm/prompt.py` | template structure or instructions change |
| `SCOPE_TAXONOMY_VERSION` | hash of the `[scopes]` section of the user's `.repogerbil.toml`, computed at load time | user edits their taxonomy |

All three flow into the cache key; bumping any one of them invalidates caches it touches.

### Layer 7 — Validation + Commit Building

Module: `src/repogerbil/refine/validator.py`

- JSON-schema-constrained output means `verb` is always valid, but double-check for robustness.
- `scope` gets trimmed, lower-kebab-cased, and checked against disallowed characters.
- If the LLM somehow produced invalid output (malformed JSON despite schema enforcement), retry once with a "reminder" append; if still invalid, raise `RefinementValidationError` and skip that commit in non-strict mode (or fail the whole run in strict mode, controlled by flag).

Module: `src/repogerbil/refine/builder.py`

- Takes the structured output, composes the final multi-line message string.
- For post-pass and on-demand modes, walks the snapshot repo in topological order, rebuilding each commit with `commit-tree` using the new message (Q6-C). Updates `refs/heads/main` at the end. Same machinery as `_commit_with_timestamp()` in `snapshot.py`.

### Layer 8 — Two-Pass Refinement

Per Q3-D, refinement runs twice:

- **Pass 1**: all groups are refined with only bootstrap examples as context. Messages are written to cache and DB but not yet applied to commits.
- **Pass 2**: all groups are re-refined with Pass 1's outputs now in the retrieval pool. The Pass 2 outputs are what get applied to commits.

Pass 1 messages are never committed — they're scaffolding for Pass 2's retrieval. This doubles LLM cost on first refinement; the cache makes subsequent refinements effectively free.

`--two-pass=false` opt-out is available for users who want single-pass for speed.

### Layer 9 — Changelog Artifact (dry-run + editable)

Per Q11, `gerbil refine --dry-run --output changelog.yaml` writes the proposed messages to a YAML file keyed by commit SHA (or group ID pre-commit):

```yaml
version: 1
snapshot_id: abc123
entries:
  - commit: 1a2b3c4
    date: 2026-06-03
    message: |
      instantiate(core): base type definitions introduced

      Introduced the base type definitions — Type, Value, and the
      primitive wrappers for string/number/bool...
    files:
      - src/pyvider/cty/types/primitive.py
      - src/pyvider/cty/types/collection.py
    source_subjects:
      - "feat: add types"
      - "types stuff"
```

Users can edit the file, delete entries (skips that commit's rewrite), or replace messages by hand. Then `gerbil refine --apply-from changelog.yaml` applies the file. Missing entries fall through to fresh generation.

This file shape is **compatible with the existing `changelog_messages` parameter** on `create_snapshot()` — a refined changelog becomes canonical input for future snapshots.

---

## Public Surfaces

### CLI

```
gerbil snapshot ... --llm-refine                # inline refinement during snapshot
gerbil snapshot ... --llm-refine --no-cache     # bypass cache
gerbil snapshot ... --llm-refine --concurrency 4

gerbil refine <snapshot-repo>                   # post-pass refinement
gerbil refine <snapshot-repo> --dry-run --output changelog.yaml
gerbil refine <snapshot-repo> --apply-from changelog.yaml
gerbil refine <snapshot-repo> --force           # bypass cache
gerbil refine <snapshot-repo> --two-pass=false
gerbil refine <snapshot-repo> --concurrency 4

gerbil vocab list                               # show allowed verbs
gerbil vectordb stats <snapshot-repo>           # collection counts
gerbil vectordb query <snapshot-repo> --similar-to <sha>
```

### MCP Server

Launched via `gerbil mcp-serve` (stdio transport). Two tools (Q12-C):

| Tool | Input | Output |
|---|---|---|
| `refine_snapshot` | `{snapshot_path, concurrency?, force?, two_pass?}` | `{refined, skipped, failed, details[]}` |
| `preview_refinement` | `{snapshot_path, output_path?}` | `{changelog_path, summary{refined, skipped}}` |

Resources exposed:
- `vocabulary://categories` — vocab JSON
- `vocabulary://scopes` — current scope taxonomy
- `prompt://refine-message` — current prompt template (versioned)

All remaining operations (embed, find-similar, regen-single, vocab-list, stats) are accessible via `gerbil` CLI, which Claude Code / Codex can invoke via bash. Granular MCP tools may graduate from CLI later.

### Configuration

`.repogerbil.toml`:

```toml
[llm]
ollama_url = "http://localhost:11434"
model = "gemma4"
temperature = 0.0
timeout_seconds = 120
concurrency = 1

[llm.cache]
enabled = true
path = ".repogerbil/llm-cache"

[vectordb]
path = ".repogerbil/vectordb"
embedder = "sentence-transformers"
embedder_model = "all-MiniLM-L6-v2"

[scopes]
"src/pyvider/cty/types/**" = "types"
"src/pyvider/cty/registry.py" = "registry"
"tests/**" = "tests"

[refine]
bootstrap_examples = true
two_pass = true
strict_validation = false
```

Env vars (flat, single-underscore, via pydantic field aliases — no `__` separator per Q9):

```
REPOGERBIL_OLLAMA_URL
REPOGERBIL_MODEL
REPOGERBIL_CONCURRENCY
REPOGERBIL_VECTORDB_PATH
REPOGERBIL_LLM_CACHE_PATH
REPOGERBIL_LLM_CACHE_ENABLED
REPOGERBIL_TWO_PASS
REPOGERBIL_STRICT_VALIDATION
```

---

## Integration Points

### `snapshot.py`

`create_snapshot()` gains parameters:
- `llm_refine: bool = False`
- `llm_config: LLMConfig | None = None` (pydantic model; falls back to global config)
- `concurrency: int = 1`

When `llm_refine=True`, `_create_commits()` routes through a new `_create_commits_with_refinement()` path that:
1. Collects file signatures per group
2. Runs the refinement pipeline (cache check → retrieve → prompt → LLM → validate → compose)
3. Passes the refined message to `_commit_with_timestamp()` instead of the parsed conventional message

Non-refine path is unchanged. 100% backward compatibility.

### `vectordb.py`

Adds a `groups` collection and methods:
- `upsert_group(group_id, file_signature, subsystem_tokens, metadata)`
- `find_similar_groups(file_signature, subsystem_tokens, n=5)`
- `group_count` property

No change to existing collections or methods.

### `vocabulary.py`

Adds:
- `VOCAB_VERSION: str` — bumped when categories/verbs change; flows into cache key.
- `allowed_verbs() -> list[str]` — returns enum for the LLM JSON schema.

### `provenance.py`

Extended to record per-commit refinement provenance (read-only from refinement's POV; written by the refine builder). Schema:

```python
@dataclass(frozen=True)
class RefinementProvenance:
    commit_sha: str
    model: str
    prompt_version: str
    vocab_version: str
    scope_taxonomy_version: str
    retrieved_context: list[str]  # group IDs used as retrieval examples
    cache_hit: bool
    refined_at: datetime
```

Stored in the `groups` collection metadata, not in git.

---

## Delivery Plan (Thin-Slice, per Approach 2)

### Iteration 1 — minimal inline refinement

**Goal:** end-to-end working path, ugly but real.

- Ollama HTTP client (real + fake)
- Hardcoded prompt, no retrieval, no cache, single-pass
- Vocab enumeration via JSON schema
- `gerbil snapshot --llm-refine` flag wired to a new message-generator path
- Output: refined message per group, applied inline during snapshot creation
- Tests: fake Ollama client with fixture responses; verify schema-valid output composes correctly

**Exit criteria:** `gerbil snapshot /Volumes/data/pyv/pyvider-cty /tmp/out --llm-refine` produces a repo with refined messages. Output quality can be mediocre at this stage.

### Iteration 2 — vector DB retrieval + cache

**Goal:** prompts grounded in historical context; repeated runs are fast.

- `groups` collection in `vectordb.py`
- Embed file signature + subsystem tokens
- Similar-group retrieval, top-K into prompt
- Content-addressed cache layer
- Seeded bootstrap examples bundled in `src/repogerbil/refine/bootstrap_examples.py`
- Scope resolver (config-first + DB-fallback; LLM-fallback deferred to iteration 3)

**Exit criteria:** second `gerbil snapshot --llm-refine` run on the same data is a cache hit for all commits. Retrieved examples visibly influence output.

### Iteration 3 — two-pass + quality

**Goal:** self-consistent history with vocabulary coherence.

- Two-pass refinement loop
- LLM-fallback scope resolution
- Validator with retry-on-malformed
- Strict vs non-strict modes
- Parallel Ollama calls via `asyncio`, `--concurrency N`

**Exit criteria:** `gerbil snapshot --llm-refine` on pyvider-cty produces a history that reads coherently across 130+ commits. Re-running with a vocab bump triggers re-refinement only for affected commits.

### Iteration 4 — post-pass CLI + changelog artifact

**Goal:** standalone `refine` command, editable changelog, reusable as snapshot input.

- `gerbil refine <repo>` subcommand
- Commit rebuilding via `commit-tree` walk
- `--dry-run --output changelog.yaml`
- `--apply-from changelog.yaml`
- Integration with existing `changelog_messages` parameter in `create_snapshot`

**Exit criteria:** produce a changelog YAML, hand-edit one entry, apply — the one entry reflects the human edit, others use the LLM output.

### Iteration 5 — MCP server

**Goal:** Claude Code / Codex integration.

- `gerbil mcp-serve` subcommand (stdio transport)
- `refine_snapshot` + `preview_refinement` tools
- `vocabulary://` and `prompt://` resources
- Plugin manifest entry in `plugins/repogerbil/.claude-plugin/plugin.json`
- Progress notifications during long refinements

**Exit criteria:** Claude Code session uses the MCP tool to refine a snapshot and display a diff. Codex integration tested.

---

## Testing Strategy

Per Q10-D:

**Mocks (core decision logic, 100% coverage):**
- `FakeOllamaClient` returning deterministic fixture responses by input hash
- `SimpleHashEmbedder` for vector DB tests (already exists)
- Unit tests for: prompt construction, JSON schema composition, cache keys, vocab validation, scope resolution, commit rebuild walk, changelog YAML round-trip

**Carveout (transport boundary):**
- `# pragma: no cover` on `HTTPOllamaClient.generate()` method body (mirrors `vectordb.py` pattern for optional-dep code)
- `pyproject.toml` `omit` list entry for `src/repogerbil/llm/http_client.py` if needed

**Realism fixtures:**
- `tests/fixtures/ollama_responses/` with a few real recorded responses from Gemma 4
- Sanity test that parses the recorded JSON to confirm schema is what Ollama actually emits
- Regenerate by running a real Ollama manually, not in CI

**Integration marker:**
- `@pytest.mark.integration` for tests that hit real Ollama
- Opt-in via `pytest -m integration`; excluded from default `make test`

---

## Risks & Open Questions

### Risk: Gemma 4 JSON-schema compliance

Some local models don't fully honor structured output constraints. Mitigation: validator with one retry, then fall back to strict-mode error or non-strict skip. Iteration 1 will surface whether this is a real problem.

### Risk: Cache-key churn from seeded examples

If bootstrap examples are part of the retrieval context and they change, every cache key changes. Mitigation: bootstrap examples have their own version string; changing them is a deliberate action that intentionally invalidates all caches.

### Risk: Pass-1-output influencing Pass-2 in unwanted ways

Two-pass may amplify bad choices (bad Pass-1 scope label gets reinforced in Pass 2). Mitigation: Pass 1 outputs are tagged in the DB with `pass=1` and optionally de-weighted or excluded from Pass-2 retrieval. Iteration 3 will tune this.

### Open: Scope label canonicalization

Who owns the "official" scope labels once they exist? If the LLM invents `core-types` today and `core_types` tomorrow, we want those collapsed. Probably a normalization pass on scope strings before DB insert. Detail for Iteration 2.

### Open: Ollama not running

Clear error message pointing at `REPOGERBIL_OLLAMA_URL` and suggesting `ollama serve`. No silent fallback.

### Deferred to future work

- Claude API as an LLM backend
- `Refined-By` git trailers (explicitly requested deferred)
- Project-level changelog synthesis
- HTTP transport for MCP
- Granular MCP tools beyond the initial 2
- Global (cross-project) cache

---

## Success Criteria

The feature is successful when:

1. A snapshot of pyvider-cty (~130 commits) produces a readable narrative history where every commit message uses the vocabulary correctly and the summaries describe what the files show changed
2. Re-running refinement is a cache-hit-dominated operation (not re-calling the LLM)
3. A human can `--dry-run`, edit two or three commit messages in the changelog YAML, and `--apply-from` that edited file — the edits land and the rest use LLM output
4. Claude Code can call `refine_snapshot` via MCP and get a structured result back
5. 100% coverage maintained; no new `type: ignore` without explanation; `make quality` passes
