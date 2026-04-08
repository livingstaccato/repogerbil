# Vector Database Design

## Purpose

Add semantic search and cross-repo intelligence to repogerbil. Instead of just listing missing dates and generating summaries from titles, the vector DB enables:

1. **Semantic search across changelogs** — "find all security-related changes across all repos"
2. **Cross-repo correlation** — "when telemetry changed sampling, which repos updated?"
3. **Smart summary generation** — surface themes and patterns, not just aggregate titles
4. **Commit deduplication** — detect when the same fix was applied across multiple repos
5. **Impact prediction** — "if I change this module, what historically breaks?"

## Storage Model

### Collections

**repos** — Repository metadata
```
{
  id: "uwarp-space",
  path: "/Users/tim/code/gh/undef-games/uwarp-space",
  first_date: "2026-02-21",
  last_date: "2026-04-07",
  total_commits: 1170,
  prefix_adoption: 0.99,
  primary_categories: ["remediate", "qualify", "instantiate"],
  dependencies: ["provide-telemetry", "provide-terminal"],
}
```

**changelogs** — Per-date changelog embeddings
```
{
  id: "uwarp-space/2026-04-07",
  repo: "uwarp-space",
  date: "2026-04-07",
  title: "TWGS Gold login compatibility...",
  summary: "Eight fixes targeting...",
  embedding: [0.12, -0.34, ...],  # from title + summary
  commits: 10,
  files_changed: 121,
  categories: {"remediate": 4, "instantiate": 1},
  bulk_files: 106,
}
```

**changes** — Individual change section embeddings
```
{
  id: "uwarp-space/2026-04-07/0",
  changelog_id: "uwarp-space/2026-04-07",
  title: "TWGS Gold BBS-authenticated login path",
  embedding: [0.45, 0.12, ...],  # from title + points
  category: "remediate",
  severity: "behavioral",
  files: ["packages/uwarp-explorer/src/uwarp_explorer/login.py"],
  impact_repos: ["bbsbot"],
}
```

**commits** — Individual commit embeddings (for dedup/search)
```
{
  id: "uwarp-space/abc1234",
  repo: "uwarp-space",
  date: "2026-04-07",
  subject: "fix(parity): sync twcfig.dat in preflight",
  embedding: [0.23, -0.56, ...],
  category: "remediate",
  files: ["packages/uwarp-explorer/src/uwarp_explorer/parity/_preflight.py"],
}
```

## Database Choice

### Recommended: ChromaDB

- **Embedded** — runs in-process, no server needed
- **SQLite backend** — single file, portable, zero config
- **Python-native** — `pip install chromadb`
- **Persistent** — data survives across runs
- **Small** — suitable for tens of thousands of documents (our scale)

```python
import chromadb

client = chromadb.PersistentClient(path=".repogerbil/vectordb")
changelogs = client.get_or_create_collection("changelogs")
changes = client.get_or_create_collection("changes")
```

### Alternative: LanceDB

- Arrow-native, faster for large datasets
- Also embedded, also Python-native
- Better for millions of documents (overkill for our scale)

### Not recommended for this use case

- Pinecone, Weaviate, Qdrant — cloud/server-based, too heavy
- FAISS — no metadata filtering, no persistence without wrapper

## Embedding Strategy

### For changelogs and changes

Embed `title + summary` or `title + points[].text` as a single document. This captures the semantic meaning of what happened.

### Embedding model

**Default: sentence-transformers/all-MiniLM-L6-v2**
- 384 dimensions, fast, good for short text
- Runs locally, no API needed
- `pip install sentence-transformers`

**Alternative: OpenAI text-embedding-3-small**
- 1536 dimensions, higher quality
- Requires API key and network
- Better for production with many repos

### Configuration

```toml
# .repogerbil.toml
[vectordb]
enabled = true
path = ".repogerbil/vectordb"
engine = "chromadb"                    # chromadb | lancedb
embedding_model = "all-MiniLM-L6-v2"  # local model
# embedding_model = "text-embedding-3-small"  # OpenAI (requires OPENAI_API_KEY)
```

## Architecture Integration

```
repogerbil/
├── core/
│   ├── vectordb.py       # Database abstraction (ChromaDB/LanceDB)
│   ├── embeddings.py     # Embedding model wrapper
│   └── search.py         # Semantic search queries
```

### vectordb.py — Database abstraction

```python
class VectorStore:
    """Abstract interface for vector storage."""
    
    def upsert_changelog(self, repo: str, date: str, data: dict) -> None: ...
    def upsert_change(self, changelog_id: str, index: int, data: dict) -> None: ...
    def search_changelogs(self, query: str, n: int = 10) -> list[dict]: ...
    def search_changes(self, query: str, n: int = 10, repo: str | None = None) -> list[dict]: ...
    def find_related(self, changelog_id: str, n: int = 5) -> list[dict]: ...
    def find_cross_repo(self, change_id: str) -> list[dict]: ...
```

### embeddings.py — Embedding model wrapper

```python
class Embedder:
    """Generate embeddings from text."""
    
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

### search.py — High-level search queries

```python
def find_security_changes(store: VectorStore) -> list[dict]:
    """Find all security-related changes across repos."""
    return store.search_changes("security vulnerability fix harden auth", n=20)

def find_correlated_work(store: VectorStore, repo: str, date: str) -> list[dict]:
    """Find work in other repos related to a specific day's changes."""
    changelog = store.get_changelog(repo, date)
    return store.find_related(changelog["id"])

def detect_duplicate_fixes(store: VectorStore, commit_subject: str) -> list[dict]:
    """Find similar commits across repos (potential duplicates)."""
    return store.search_commits(commit_subject, n=5, threshold=0.85)
```

## CLI Commands

```bash
# Index all changelogs into the vector DB
repogerbil index /path/to/changelogs

# Semantic search across all changelogs
repogerbil search "security hardening" --top 10

# Find related work across repos for a specific date
repogerbil related uwarp-space --date 2026-04-07

# Find similar commits (deduplication check)
repogerbil similar "fix(parity): sync twcfig.dat"

# Show cross-repo impact for a change
repogerbil impact provide-telemetry --date 2026-04-07
```

## Indexing Pipeline

```
changelog YAML → parse → extract text → embed → upsert to vectordb
```

The `index` command:
1. Walks all changelog YAML files in the directory
2. For each file: extracts title, summary, change titles, point texts
3. Generates embeddings (batched for efficiency)
4. Upserts into the appropriate collection with metadata
5. Incremental: skips files already indexed (by hash or mtime)

## Data Size Estimates

For ~2,700 changelog files across 20+ repos:
- ~2,700 changelog documents (title + summary embeddings)
- ~10,000 change section documents
- ~25,000 commit documents (optional, for dedup)
- ChromaDB storage: ~50MB with MiniLM embeddings
- Indexing time: ~5 minutes initial, <1 minute incremental

## Dependencies (optional)

```toml
[project.optional-dependencies]
vectordb = [
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
]
```

Install with: `pip install repogerbil[vectordb]`

The vector DB is an optional feature — all core repogerbil functionality works without it. The `index`, `search`, `related`, `similar`, and `impact` commands are only available when the `vectordb` extra is installed.

## Implementation Order

1. **vectordb.py** — ChromaDB wrapper with collection management
2. **embeddings.py** — sentence-transformers wrapper
3. **search.py** — high-level query functions
4. **CLI `index` command** — batch indexing from changelog YAML
5. **CLI `search` command** — semantic search
6. **CLI `related` / `similar` / `impact`** — cross-repo queries
7. **Integration with `summary`** — use vector search for smarter weekly narratives
