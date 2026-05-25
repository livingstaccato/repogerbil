# Vulture whitelist — symbols that frameworks (pydantic, Click) reference at
# runtime in ways vulture's static analysis can't see.
#
# Audited 2026-05-24. Re-audit procedure:
#   1. Run `make dead-code` — should exit 0 with the current whitelist.
#   2. Run the same command with `vulture_whitelist.py` replaced by an empty
#      file (e.g. `--exclude src/repogerbil/core/config.py,vulture_whitelist.py`).
#   3. Any *new* findings at confidence >= 80 must either be a real fix in the
#      source or a new whitelist entry here (prefer the former).
#
# Keep entries minimal: only the pydantic-settings hooks that look unused to
# vulture but are invoked by pydantic itself. Click commands registered via the
# ``@cli.command`` decorator and pydantic model fields used by consumers do not
# need entries at the current confidence threshold — adding them masks real
# regressions.

# pydantic-settings hook (called by pydantic, not user code)
from repogerbil.core.config import Settings

Settings.model_config
Settings.settings_customise_sources
