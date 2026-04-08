# Changelog Vocabulary

## Categories

What kind of work was done.

| Term | Conventional | Description |
|------|-------------|-------------|
| `instantiate` | feat | New capability, feature, or behavior |
| `remediate` | fix | Correcting broken or incorrect behavior |
| `decouple` | refactor | Reducing coupling, improving modularity |
| `deprecate` | remove | Retiring dead, unused, or redundant code |
| `interface` | feat | Defining connections between subsystems |
| `specify` | docs | Documentation, specs, making implicit explicit |
| `qualify` | test | Tests, assertions, verification |
| `margin` | fix | Adding buffer or slack (timeouts, rate limits) |
| `harden` | fix | Resisting failure or attack (validation, retries) |
| `streamline` | perf | Performance optimization |
| `baseline` | chore | Dependencies, config, environment changes |

## Severities

Scope and impact of the change.

| Term | Semver | Description |
|------|--------|-------------|
| `architectural` | major | Breaking change or foundational redesign |
| `behavioral` | minor | Observable behavior change, non-breaking |
| `internal` | patch | Implementation detail only |
| `errata` | — | Cosmetic, near-invisible |

## Commit Prefix Mapping

| Prefix | Category | Notes |
|--------|----------|-------|
| `feat:` | instantiate | Or `interface` if mentions API/protocol |
| `fix:` | remediate | Or `harden` (security) or `margin` (timeout) |
| `refactor:` | decouple | |
| `test:` | qualify | |
| `perf:` | streamline | |
| `docs:` | specify | |
| `chore:` | baseline | Also `ci:`, `build:`, `style:` |
| `revert:` | deprecate | |
| `feat!:` | instantiate | Severity → architectural (breaking) |

## Verb Heuristics

For commits without conventional prefixes, the leading verb is matched:

| Verbs | Category |
|-------|----------|
| add, implement, create, introduce | instantiate |
| fix, repair, correct, resolve | remediate |
| remove, delete, drop, clean up | deprecate |
| refactor, extract, restructure, split, move | decouple |
| update, upgrade, bump, pin | baseline |
| test, verify | qualify |
| improve, optimize, speed up | streamline |
| harden, guard, validate | harden |
| limit | margin |
| document | specify |

Past tense variants (added, fixed, removed, etc.) are also matched.
