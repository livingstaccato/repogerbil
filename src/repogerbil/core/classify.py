# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Commit classification — conventional prefixes, verb heuristics, file rules."""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import re

from repogerbil.core.config import FileRule, Settings
from repogerbil.core.vocabulary import PREFIX_TO_CATEGORY, SEVERITIES

_PREFIX_RE = re.compile(r"^(\w+)(?:\([^)]*\))?(!)?:\s*")

_HARDEN_RE = re.compile(
    r"secur|harden|guard|resilien|sanitiz|validat|auth|permiss|trust|attack",
    re.IGNORECASE,
)
_MARGIN_RE = re.compile(
    r"timeout|buffer|limit|backoff|throttl|rate.limit|headroom|retry|cap\b",
    re.IGNORECASE,
)
_INTERFACE_RE = re.compile(
    r"\bAPI\b|protocol|endpoint|interface|connect|transport|websocket|grpc",
    re.IGNORECASE,
)

_VERB_MAP: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^add(?:ed|s)?\b", re.I), "instantiate", "behavioral"),
    (re.compile(r"^implement(?:ed|s)?\b", re.I), "instantiate", "behavioral"),
    (re.compile(r"^creat(?:e[ds]?|ing)\b", re.I), "instantiate", "behavioral"),
    (re.compile(r"^introduc(?:e[ds]?|ing)\b", re.I), "instantiate", "behavioral"),
    (re.compile(r"^wire[ds]?\b", re.I), "interface", "behavioral"),
    (re.compile(r"^connect(?:ed|s)?\b", re.I), "interface", "behavioral"),
    (re.compile(r"^fix(?:ed|es)?\b", re.I), "remediate", "behavioral"),
    (re.compile(r"^repair(?:ed|s)?\b", re.I), "remediate", "behavioral"),
    (re.compile(r"^correct(?:ed|s)?\b", re.I), "remediate", "behavioral"),
    (re.compile(r"^resolv(?:e[ds]?|ing)\b", re.I), "remediate", "behavioral"),
    (re.compile(r"^remov(?:e[ds]?|ing)\b", re.I), "deprecate", "internal"),
    (re.compile(r"^delet(?:e[ds]?|ing)\b", re.I), "deprecate", "internal"),
    (re.compile(r"^drop(?:ped|s)?\b", re.I), "deprecate", "internal"),
    (re.compile(r"^clean(?:ed|s|ing)?\s?up\b", re.I), "deprecate", "internal"),
    (re.compile(r"^refactor(?:ed|s|ing)?\b", re.I), "decouple", "internal"),
    (re.compile(r"^extract(?:ed|s|ing)?\b", re.I), "decouple", "internal"),
    (re.compile(r"^restructur(?:e[ds]?|ing)\b", re.I), "decouple", "internal"),
    (re.compile(r"^split(?:ting)?\b", re.I), "decouple", "internal"),
    (re.compile(r"^mov(?:e[ds]?|ing)\b", re.I), "decouple", "internal"),
    (re.compile(r"^renam(?:e[ds]?|ing)\b", re.I), "decouple", "errata"),
    (re.compile(r"^migrat(?:e[ds]?|ing)\b", re.I), "decouple", "behavioral"),
    (re.compile(r"^updat(?:e[ds]?|ing)\b", re.I), "baseline", "internal"),
    (re.compile(r"^upgrad(?:e[ds]?|ing)\b", re.I), "baseline", "internal"),
    (re.compile(r"^bump(?:ed|s)?\b", re.I), "baseline", "errata"),
    (re.compile(r"^pin(?:ned|s)?\b", re.I), "baseline", "internal"),
    (re.compile(r"^test(?:ed|s|ing)?\b", re.I), "qualify", "internal"),
    (re.compile(r"^verif(?:y|ied|ies|ying)\b", re.I), "qualify", "internal"),
    (re.compile(r"^document(?:ed|s|ing)?\b", re.I), "specify", "errata"),
    (re.compile(r"^improv(?:e[ds]?|ing)\b", re.I), "streamline", "behavioral"),
    (re.compile(r"^optimiz(?:e[ds]?|ing)\b", re.I), "streamline", "behavioral"),
    (re.compile(r"^speed(?:ing)?\s?up\b", re.I), "streamline", "behavioral"),
    (re.compile(r"^harden(?:ed|s|ing)?\b", re.I), "harden", "behavioral"),
    (re.compile(r"^guard(?:ed|s|ing)?\b", re.I), "harden", "behavioral"),
    (re.compile(r"^validat(?:e[ds]?|ing)\b", re.I), "harden", "behavioral"),
    (re.compile(r"^limit(?:ed|s|ing)?\b", re.I), "margin", "behavioral"),
    (re.compile(r"^increas(?:e[ds]?|ing)\b.*timeout", re.I), "margin", "behavioral"),
    (re.compile(r"^v?\d+\.\d+", re.I), "baseline", "errata"),
]

# Prefix → severity for non-behavioral prefixes
_PREFIX_SEVERITY: dict[str, str] = {
    "chore": "internal",
    "ci": "internal",
    "build": "internal",
    "style": "internal",
    "config": "internal",
    "release": "internal",
    "docs": "errata",
    "doc": "errata",
    "spec": "errata",
    "test": "internal",
    "refactor": "internal",
    "rename": "internal",
}


@dataclass(frozen=True)
class Classification:
    """Result of classifying a commit."""

    category: str | None
    severity: str | None
    needs_review: bool


def classify_commit(
    subject: str,
    body: str = "",
    auto_breaking: bool = True,
    settings: Settings | None = None,
) -> Classification:
    """Classify a commit by its subject line.

    Tries conventional prefix first, then verb heuristics.
    Returns Classification with needs_review=True when unclassifiable.
    """
    if subject.lower().startswith("merge"):
        vocab = settings.vocabulary if settings else None
        sev_map = vocab.severities if vocab else SEVERITIES
        return Classification(category="baseline", severity=sev_map.get("errata"), needs_review=False)

    vocab = settings.vocabulary if settings else None

    result = _try_conventional_prefix(subject, body, auto_breaking, vocab)
    if result is not None:
        return result

    result = _try_verb_heuristic(subject)
    if result is not None:
        return result

    return Classification(category=None, severity=None, needs_review=True)


def _try_conventional_prefix(
    subject: str,
    body: str,
    auto_breaking: bool,
    vocab: VocabularyConfig | None = None,
) -> Classification | None:
    """Try to classify using conventional commit prefix."""
    m = _PREFIX_RE.match(subject)
    if not m:
        return None

    prefix = m.group(1).lower()
    is_breaking = bool(m.group(2))

    prefix_map = vocab.prefix_to_category if vocab else PREFIX_TO_CATEGORY
    category = prefix_map.get(prefix)
    if not category:
        return None

    severity = "behavioral"

    if auto_breaking and (is_breaking or "BREAKING CHANGE:" in body):
        severity = "architectural"
    elif prefix == "fix":
        if _HARDEN_RE.search(subject):
            category = "harden"
        elif _MARGIN_RE.search(subject):
            category = "margin"

    if prefix == "feat" and _INTERFACE_RE.search(subject):
        category = "interface"

    if severity != "architectural":
        if prefix in _PREFIX_SEVERITY:
            severity = _PREFIX_SEVERITY[prefix]

    sev_map = vocab.severities if vocab else SEVERITIES
    severity = sev_map.get(severity, severity)

    return Classification(category=category, severity=severity, needs_review=False)


def _try_verb_heuristic(subject: str) -> Classification | None:
    """Try to classify using leading-verb heuristics."""
    for pattern, cat, sev in _VERB_MAP:
        if pattern.search(subject):
            if cat == "remediate":
                if _HARDEN_RE.search(subject):
                    cat = "harden"
                elif _MARGIN_RE.search(subject):
                    cat = "margin"
            return Classification(category=cat, severity=sev, needs_review=False)
    return None


@dataclass(frozen=True)
class FileClassification:
    """Result of classifying files by rules."""

    meaningful: list[str]
    bulk_entries: list[dict[str, object]]
    forced_categories: dict[str, str]


def classify_files(files: list[str], rules: list[FileRule]) -> FileClassification:
    """Separate files based on file rules.

    Returns FileClassification with:
    - meaningful: files not matched, or matched by "classify" action
    - bulk_entries: aggregated counts for "bulk" action rules
    - forced_categories: {filepath: category} for "classify" matches
    """
    meaningful: list[str] = []
    rule_counts: dict[int, int] = {}
    forced: dict[str, str] = {}

    for filepath in files:
        matched = False  # pragma: no mutate
        for i, rule in enumerate(rules):
            if fnmatch.fnmatch(filepath, rule.pattern):
                if rule.action == "skip":
                    pass
                elif rule.action == "bulk":
                    rule_counts[i] = rule_counts.get(i, 0) + 1
                else:  # classify — only remaining Literal value
                    if rule.category:
                        forced[filepath] = rule.category
                    meaningful.append(filepath)
                matched = True
                break
        if not matched:
            meaningful.append(filepath)

    bulk_entries: list[dict[str, object]] = []
    for i, count in sorted(rule_counts.items()):
        rule = rules[i]
        bulk_entries.append(
            {
                "category": rule.category or "baseline",
                "files": count,
                "reason": rule.reason or f"Files matching {rule.pattern}",
            }
        )

    return FileClassification(
        meaningful=meaningful,
        bulk_entries=bulk_entries,
        forced_categories=forced,
    )
