# Integration Guide

repogerbil uses a shared plugin directory at `plugins/repogerbil/`. Claude Code reads the Claude manifest in `.claude-plugin/`, and Codex reads the Codex manifest in `.codex-plugin/`.

## With Claude Code

### Plugin Installation

**Development / testing:**

```bash
claude --plugin-dir ./plugins
```

**Permanent install (via marketplace):**

```bash
# Add marketplace (once)
/plugin marketplace add livingstaccato/repogerbil

# Install
/plugin install repogerbil@livingstaccato-repogerbil

# Reload to activate
/reload-plugins
```

### Usage

```
/gerbil                     # context-aware — detects repo, suggests work
/gerbil audit --show-bad    # direct command
/gerbil catch up            # conversational — asks what to do
```

## With Codex

### Plugin Layout

- Plugin root: `plugins/repogerbil/`
- Codex manifest: `plugins/repogerbil/.codex-plugin/plugin.json`
- Local marketplace entry: `.agents/plugins/marketplace.json`

### Installed Package Flow

Use the bundled installer when `repogerbil` is installed via `uv tool install` or run with `uvx`:

```bash
uvx repogerbil plugin install --target codex
```

That installs:
- `~/plugins/repogerbil/`
- `~/.agents/plugins/marketplace.json`

### Notes

- The Codex and Claude integrations share the same `skills/` and `agents/` directories.
- If you distribute this repository, keep the `plugins/` tree and `.agents/plugins/marketplace.json` together so Codex can discover the local plugin metadata.
