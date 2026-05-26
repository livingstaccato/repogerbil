# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for provenance-aware source resolution.

This file is a worked example of migrating off the historical ``_init_repo``
helper to the shared ``git_repo`` / ``make_git_repo`` fixtures defined in
``tests/conftest.py``. The primary repo for each test comes from
``git_repo``; secondary repos (backup history sources) are created via the
``make_git_repo`` factory so we never re-implement the same defaults.
"""

from collections.abc import Callable
from pathlib import Path
import subprocess

from repogerbil.core.audit import MissingDate, find_missing
from repogerbil.core.provenance import (
    _candidate_pairs,
    _get_hidden_commits_for_date,
    _resolve_git_root,
    collect_effective_dates,
    describe_resolution,
    resolve_provenance,
)


def _commit(repo: Path, filename: str, text: str, message: str, date: str) -> None:
    env = {"HOME": str(repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / filename).write_text(text)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": f"{date}T10:00:00", "GIT_COMMITTER_DATE": f"{date}T10:00:00"},
    )


def _add_hidden_commit(repo: Path) -> None:
    """Add the visible+hidden commit pair used across resolution tests."""
    _commit(repo, "visible.py", "print('visible')\n", "feat: visible", "2025-07-23")
    subprocess.run(["git", "checkout", "-b", "hidden"], cwd=repo, capture_output=True, check=True)
    _commit(repo, "hidden.py", "print('hidden')\n", "feat: hidden", "2025-07-28")
    subprocess.run(["git", "checkout", "-"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "branch", "-D", "hidden"], cwd=repo, capture_output=True, check=True)


class TestProvenanceResolution:
    def test_resolves_visible_commits(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-23", git_repo, include_files=True)
        assert res.mode == "visible"
        assert len(res.commits) == 1
        assert res.stats is not None
        assert res.stats.commits == 1

    def test_resolves_hidden_ref_commits(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_files=True)
        assert res.mode == "hidden_ref"
        assert len(res.commits) == 1
        assert res.commits[0].subject == "feat: hidden"
        assert res.stats is not None

    def test_resolves_backup_source(self, make_git_repo: Callable[[str], Path], git_repo: Path) -> None:
        backup = make_git_repo("backup")
        _commit(backup, "old.py", "print('old')\n", "feat: old era", "2025-02-03")

        res = resolve_provenance("primary", "2025-02-03", git_repo, extra_sources=[backup], include_files=True)
        assert res.mode == "backup"
        assert res.source_path == str(backup)
        assert len(res.commits) == 1
        assert res.commits[0].subject == "feat: old era"

    def test_unresolved_without_hidden_refs(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_hidden_refs=False)
        assert res.mode == "unresolved"
        assert res.source_path is None
        assert res.notes

    def test_no_git_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing"
        res = resolve_provenance("missing", "2025-07-28", missing)
        assert res.mode == "unresolved"
        assert res.source_path is None
        assert "no git root" in res.notes[0]

    def test_nested_file_path_resolves_root(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        file_path = git_repo / "visible.py"
        res = resolve_provenance("primary", "2025-07-23", file_path, include_hidden_refs=False)
        assert res.mode == "visible"
        assert res.source_path == str(git_repo)

    def test_describe_resolution(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-23", git_repo)
        lines = describe_resolution(res)
        assert any("primary/2025-07-23" in line for line in lines)
        assert any("candidate" in line for line in lines)

    def test_describe_unresolved(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_hidden_refs=False)
        lines = describe_resolution(res)
        assert any("note:" in line for line in lines)

    def test_duplicate_extra_source_roots_are_ignored(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        nested = git_repo / "nested"
        nested.mkdir()
        res = resolve_provenance("primary", "2025-07-29", git_repo, extra_sources=[nested])
        assert res.mode == "unresolved"
        assert len(res.candidates) == 2


class TestEffectiveDates:
    def test_collects_visible_and_hidden_dates(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        dates = collect_effective_dates(git_repo)
        assert "2025-07-23" in dates
        assert "2025-07-28" in dates

    def test_collects_union_from_extra_sources(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        backup = make_git_repo("backup")
        _commit(git_repo, "primary.py", "print('primary')\n", "feat: primary", "2025-07-23")
        _commit(backup, "backup.py", "print('backup')\n", "feat: backup", "2025-07-28")

        dates = collect_effective_dates(git_repo, extra_sources=[backup])
        assert dates == {"2025-07-23", "2025-07-28"}

    def test_without_hidden_refs(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        dates = collect_effective_dates(git_repo, include_hidden_refs=False)
        assert "2025-07-23" in dates
        assert "2025-07-28" not in dates


class TestMissingWithHiddenRefs:
    def test_missing_reports_hidden_ref_date(self, tmp_path: Path, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        cl_dir = tmp_path / "changelogs"
        repo_dir = cl_dir / "primary"
        repo_dir.mkdir(parents=True)
        (repo_dir / "2025-07-23-primary-changelog.yaml").write_text("date: 2025-07-23\nrepo: primary\n")

        result = find_missing({"primary": str(git_repo)}, cl_dir)
        assert MissingDate(repo="primary", date="2025-07-28") in result

    def test_missing_with_backup_source(
        self, tmp_path: Path, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        backup = make_git_repo("backup")
        _commit(git_repo, "primary.py", "print('primary')\n", "feat: primary", "2025-02-02")
        _commit(backup, "old.py", "print('old')\n", "feat: old era", "2025-02-03")
        cl_dir = tmp_path / "changelogs"
        repo_dir = cl_dir / "primary"
        repo_dir.mkdir(parents=True)
        (repo_dir / "2025-02-02-primary-changelog.yaml").write_text("date: 2025-02-02\nrepo: primary\n")

        result = find_missing({"primary": str(git_repo)}, cl_dir, extra_sources=[backup])
        assert MissingDate(repo="primary", date="2025-02-03") in result


class TestResolveProvenanceMutationCoverage:
    """Targeted assertions to pin exact string literals, arg propagation, defaults."""

    def test_no_git_root_populates_repo_and_date_and_candidates_and_note(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent"
        res = resolve_provenance("repoX", "2025-01-15", missing)
        # Pin repo and date attributes exactly (kills repo=None, date=None mutations)
        assert res.repo == "repoX"
        assert res.date == "2025-01-15"
        assert res.source_path is None
        assert res.mode == "unresolved"
        # Pin candidates field exactly (kills candidates=None and dropped-kwarg mutations)
        assert res.candidates == []
        assert isinstance(res.candidates, list)
        # Pin exact note text
        assert len(res.notes) == 1
        assert res.notes[0] == f"no git root found for {missing}"

    def test_unresolved_after_search_populates_repo_date_and_exact_note(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primaryR", "2099-12-31", git_repo, include_hidden_refs=True)
        assert res.repo == "primaryR"
        assert res.date == "2099-12-31"
        assert res.source_path is None
        assert res.mode == "unresolved"
        # Pin exact note string (kills XX...XX and UPPERCASE mutations)
        assert res.notes == ["no candidate source contained commits for the requested date"]

    def test_visible_candidate_has_exact_mode_reason_paths_and_count(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-23", git_repo)
        assert res.mode == "visible"
        # Exactly one candidate should be appended for the visible-hit path
        assert len(res.candidates) == 1
        cand = res.candidates[0]
        assert cand.mode == "visible"
        # Exact strings pin the visible-reason literal
        assert cand.reason == "visible history contains commits"
        # Path propagation: input_path mirrors input_hint, resolved_path mirrors git root
        assert cand.input_path == str(git_repo)
        assert cand.resolved_path == str(git_repo)
        # commit_count must be the actual count, not None / 0 / sentinel
        assert cand.commit_count == 1

    def test_hidden_candidate_has_exact_mode_reason_and_count(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo)
        assert res.mode == "hidden_ref"
        # Two candidates expected: one visible (miss), one hidden (hit)
        assert len(res.candidates) == 2
        visible_cand, hidden_cand = res.candidates
        # Visible miss path: exact reason
        assert visible_cand.mode == "visible"
        assert visible_cand.reason == "no visible commits for date"
        assert visible_cand.commit_count == 0
        assert visible_cand.input_path == str(git_repo)
        assert visible_cand.resolved_path == str(git_repo)
        # Hidden hit path: exact mode + reason
        assert hidden_cand.mode == "hidden_ref"
        assert hidden_cand.reason == "hidden unreachable commit contains date"
        assert hidden_cand.commit_count == 1
        assert hidden_cand.input_path == str(git_repo)
        assert hidden_cand.resolved_path == str(git_repo)

    def test_backup_source_visible_candidate_mode_is_backup_with_input_path(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        backup = make_git_repo("backup")
        _commit(backup, "old.py", "print('old')\n", "feat: old era", "2025-02-03")
        res = resolve_provenance("primary", "2025-02-03", git_repo, extra_sources=[backup])
        # The hit comes from the backup repo, so the matched candidate is mode=backup
        backup_cands = [c for c in res.candidates if c.input_path == str(backup)]
        assert len(backup_cands) == 1
        bc = backup_cands[0]
        assert bc.mode == "backup"
        assert bc.resolved_path == str(backup)
        assert bc.reason == "visible history contains commits"
        assert bc.commit_count == 1

    def test_backup_hidden_candidate_mode_is_backup_not_hidden_ref(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        """Even for hidden hits, a non-primary source uses mode='backup' for its
        candidate row — pins the `"hidden_ref" if is_primary else "backup"` branch."""
        backup = make_git_repo("backup")
        # Visible commit on backup so the primary repo misses both visible and hidden,
        # and the backup also enters its hidden-ref branch.
        _commit(backup, "v.py", "v", "feat: v", "2024-01-01")
        # Add a hidden commit on backup for a different date we want to resolve
        _commit(backup, "v2.py", "v2", "feat: v2", "2024-01-01")
        subprocess.run(["git", "checkout", "-b", "h"], cwd=backup, capture_output=True, check=True)
        _commit(backup, "h.py", "h", "feat: h", "2024-06-15")
        subprocess.run(["git", "checkout", "-"], cwd=backup, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "h"], cwd=backup, capture_output=True, check=True)

        res = resolve_provenance(
            "primary", "2024-06-15", git_repo, extra_sources=[backup], include_hidden_refs=True
        )
        assert res.mode == "backup"
        # Find the hidden candidate for the backup (the second backup candidate)
        backup_cands = [c for c in res.candidates if c.input_path == str(backup)]
        # Expect at least 2 candidates for backup: visible miss + hidden hit, both mode="backup"
        assert len(backup_cands) >= 2
        # The hidden-hit candidate must have mode="backup" (not "hidden_ref")
        hidden_hit = [c for c in backup_cands if c.commit_count > 0 and c.reason.startswith("hidden")]
        assert len(hidden_hit) == 1
        assert hidden_hit[0].mode == "backup"
        assert hidden_hit[0].reason == "hidden unreachable commit contains date"

    def test_default_include_hidden_refs_is_true(self, git_repo: Path) -> None:
        """Default include_hidden_refs=True: hidden commits should resolve without explicit flag."""
        _add_hidden_commit(git_repo)
        # Call WITHOUT passing include_hidden_refs to assert the default value
        res = resolve_provenance("primary", "2025-07-28", git_repo)
        assert res.mode == "hidden_ref"

    def test_default_include_files_is_false(self, git_repo: Path) -> None:
        """Default include_files=False: returned commits should NOT carry file lists."""
        _commit(git_repo, "a.py", "a", "feat: a", "2025-03-15")
        res = resolve_provenance("primary", "2025-03-15", git_repo)
        assert res.mode == "visible"
        assert len(res.commits) == 1
        # With include_files=False default, files list should be empty
        assert res.commits[0].files == []

    def test_include_files_true_propagates_to_visible_commits(self, git_repo: Path) -> None:
        """include_files=True must propagate so commits carry their file lists."""
        _commit(git_repo, "tracked.py", "x", "feat: x", "2025-03-16")
        res = resolve_provenance("primary", "2025-03-16", git_repo, include_files=True)
        assert res.mode == "visible"
        assert len(res.commits) == 1
        assert "tracked.py" in res.commits[0].files

    def test_include_files_true_propagates_to_hidden_commits(self, git_repo: Path) -> None:
        """include_files=True must propagate to hidden-ref commit retrieval too."""
        _commit(git_repo, "visible.py", "v", "feat: visible", "2025-04-01")
        subprocess.run(["git", "checkout", "-b", "hide"], cwd=git_repo, capture_output=True, check=True)
        _commit(git_repo, "hidden_tracked.py", "h", "feat: hidden_tr", "2025-04-02")
        subprocess.run(["git", "checkout", "-"], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "hide"], cwd=git_repo, capture_output=True, check=True)
        res = resolve_provenance("primary", "2025-04-02", git_repo, include_files=True)
        assert res.mode == "hidden_ref"
        assert len(res.commits) == 1
        assert "hidden_tracked.py" in res.commits[0].files

    def test_default_message_depth_subject_yields_empty_body(self, git_repo: Path) -> None:
        """Default message_depth='subject' must produce empty body on returned commits."""
        env = {"HOME": str(git_repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (git_repo / "f.py").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: with-body\n\nbody-line-1\nbody-line-2"],
            cwd=git_repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2025-05-10T10:00:00", "GIT_COMMITTER_DATE": "2025-05-10T10:00:00"},
        )
        res = resolve_provenance("primary", "2025-05-10", git_repo)
        assert res.mode == "visible"
        assert len(res.commits) == 1
        assert res.commits[0].body == ""

    def test_message_depth_full_propagates_for_visible(self, git_repo: Path) -> None:
        """message_depth='full' must propagate so commit body is populated."""
        env = {"HOME": str(git_repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (git_repo / "f.py").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: with-body\n\nMARKERLINE-VISIBLE"],
            cwd=git_repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2025-05-11T10:00:00", "GIT_COMMITTER_DATE": "2025-05-11T10:00:00"},
        )
        res = resolve_provenance("primary", "2025-05-11", git_repo, message_depth="full")
        assert res.mode == "visible"
        assert len(res.commits) == 1
        assert "MARKERLINE-VISIBLE" in res.commits[0].body

    def test_message_depth_full_propagates_for_hidden(self, git_repo: Path) -> None:
        """message_depth='full' must propagate into hidden-ref commit fetching."""
        _commit(git_repo, "visible.py", "v", "feat: v", "2025-06-01")
        subprocess.run(["git", "checkout", "-b", "hh"], cwd=git_repo, capture_output=True, check=True)
        env = {"HOME": str(git_repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (git_repo / "h.py").write_text("h\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: hidden\n\nMARKERLINE-HIDDEN"],
            cwd=git_repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2025-06-02T10:00:00", "GIT_COMMITTER_DATE": "2025-06-02T10:00:00"},
        )
        subprocess.run(["git", "checkout", "-"], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "hh"], cwd=git_repo, capture_output=True, check=True)
        res = resolve_provenance("primary", "2025-06-02", git_repo, message_depth="full")
        assert res.mode == "hidden_ref"
        assert len(res.commits) == 1
        assert "MARKERLINE-HIDDEN" in res.commits[0].body

    def test_include_hidden_refs_false_continues_to_next_source(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        """When include_hidden_refs=False and the primary misses, the loop must
        CONTINUE to the backup source (not break out)."""
        backup = make_git_repo("backup")
        _commit(backup, "b.py", "b", "feat: b", "2025-08-15")
        res = resolve_provenance(
            "primary", "2025-08-15", git_repo, extra_sources=[backup], include_hidden_refs=False
        )
        # Backup must be reached and produce a hit
        assert res.mode == "backup"
        assert res.source_path == str(backup)
        assert len(res.commits) == 1

    def test_visible_and_hidden_use_same_primary_input_hint(self, git_repo: Path) -> None:
        """is_primary must remain True only when BOTH conditions hold —
        the and/or mutation flip would mislabel a duplicate-root extra_source."""
        # extra_source pointing to the same git root as primary, but with a different
        # input_hint (a subdir). The primary already appears first in _candidate_pairs,
        # so only one (path, root) pair survives — assert it's labelled visible.
        sub = git_repo / "sub"
        sub.mkdir()
        _commit(git_repo, "x.py", "x", "feat: x", "2025-09-09")
        res = resolve_provenance("primary", "2025-09-09", git_repo, extra_sources=[sub])
        assert res.mode == "visible"
        # Only the primary's pair remains (sub dedups via resolve()); first cand mode=="visible"
        assert res.candidates[0].mode == "visible"

    def test_unresolved_includes_both_visible_and_hidden_candidate_rows(self, git_repo: Path) -> None:
        """When nothing matches, both visible and hidden-ref candidate rows must
        appear with their exact miss-reason strings."""
        _commit(git_repo, "a.py", "a", "feat: a", "2025-10-01")
        res = resolve_provenance("primary", "2025-10-15", git_repo, include_hidden_refs=True)
        assert res.mode == "unresolved"
        assert len(res.candidates) == 2
        # First is visible-miss, second is hidden-miss
        assert res.candidates[0].reason == "no visible commits for date"
        assert res.candidates[1].reason == "no hidden commits for date"
        assert res.candidates[0].mode == "visible"
        assert res.candidates[1].mode == "hidden_ref"


class TestFinalizeResolutionStats:
    """Pin _finalize_resolution arg propagation (commits[0].hash, commits[-1].hash)."""

    def test_diff_stats_span_full_range_when_first_and_last_differ(self, git_repo: Path) -> None:
        # Earlier seed commit on a DIFFERENT date so commits[0] for the target date
        # is NOT the root commit — this means commits[0].hash actually matters for
        # the diff range (otherwise --root fallback would mask any None mutation).
        _commit(git_repo, "seed.py", "seed\n", "chore: seed", "2025-10-30")
        # Two commits on the same target date so commits[0] != commits[-1]
        _commit(git_repo, "a.py", "alpha\n", "feat: a", "2025-11-01")
        _commit(git_repo, "b.py", "beta\nbeta2\n", "feat: b", "2025-11-01")
        res = resolve_provenance("primary", "2025-11-01", git_repo, include_files=True)
        assert res.stats is not None
        # The aggregate insertion count must cover BOTH date-target files (3 lines)
        # without including the seed commit. If commits[0].hash were mutated to None,
        # the get_diff_stats fallback would use --root commits[-1] and pick up seed.
        assert res.stats.insertions == 3
        assert res.stats.files_changed == 2
        assert res.stats.commits == 2


class TestCollectEffectiveDatesDefault:
    def test_default_include_hidden_refs_true_collects_hidden(self, git_repo: Path) -> None:
        """Default include_hidden_refs=True so hidden commits surface without the flag."""
        _add_hidden_commit(git_repo)
        dates = collect_effective_dates(git_repo)
        # Hidden date present without passing include_hidden_refs explicitly
        assert "2025-07-28" in dates


class TestCandidatePairsBranchControl:
    """The two `continue`->`break` mutations in _candidate_pairs."""

    def test_invalid_path_does_not_truncate_search(self, git_repo: Path, tmp_path: Path) -> None:
        """If the FIRST path in the list fails to resolve, we must CONTINUE to the
        remaining paths — a `break` mutation would skip the valid git_repo."""
        bogus = tmp_path / "totally" / "missing" / "tree"
        pairs = _candidate_pairs(bogus, [git_repo])
        # Must include the git_repo despite the unresolvable first entry
        assert len(pairs) == 1
        assert pairs[0][0] == git_repo
        assert pairs[0][1] == git_repo

    def test_duplicate_root_does_not_truncate_search(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        """If a duplicate root is seen, the loop must CONTINUE so later distinct
        repos are still added — a `break` mutation would lose `other`."""
        other = make_git_repo("other")
        sub = git_repo / "sub"
        sub.mkdir()
        # Order: primary, duplicate-of-primary (sub), distinct other
        pairs = _candidate_pairs(git_repo, [sub, other])
        keys = {str(root.resolve()) for _, root in pairs}
        assert str(git_repo.resolve()) in keys
        assert str(other.resolve()) in keys
        assert len(pairs) == 2


class TestResolveGitRootLoopExit:
    """Pin the `parent == current` loop-exit check in _resolve_git_root."""

    def test_walks_up_from_nested_subdir_to_find_git_root(self, git_repo: Path) -> None:
        deep = git_repo / "a" / "b" / "c"
        deep.mkdir(parents=True)
        # Walking up must find git_repo's .git — a `parent != current` flip would
        # return None on the first non-match.
        assert _resolve_git_root(deep) == git_repo


class TestGetHiddenCommitsForDate:
    """Pin _get_hidden_commits_for_date arg propagation + sort ordering."""

    def test_propagates_message_depth_full(self, git_repo: Path) -> None:
        _commit(git_repo, "v.py", "v", "feat: v", "2025-12-01")
        subprocess.run(["git", "checkout", "-b", "x"], cwd=git_repo, capture_output=True, check=True)
        env = {"HOME": str(git_repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (git_repo / "hh.py").write_text("h\n")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: hidden\n\nBODYTOKEN-XYZ"],
            cwd=git_repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2025-12-02T10:00:00", "GIT_COMMITTER_DATE": "2025-12-02T10:00:00"},
        )
        subprocess.run(["git", "checkout", "-"], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "x"], cwd=git_repo, capture_output=True, check=True)
        out = _get_hidden_commits_for_date(git_repo, "2025-12-02", message_depth="full", include_files=False)
        assert len(out) == 1
        assert "BODYTOKEN-XYZ" in out[0].body

    def test_propagates_include_files_true(self, git_repo: Path) -> None:
        _commit(git_repo, "v.py", "v", "feat: v", "2025-12-10")
        subprocess.run(["git", "checkout", "-b", "y"], cwd=git_repo, capture_output=True, check=True)
        _commit(git_repo, "tracked_hidden.py", "h", "feat: hh", "2025-12-11")
        subprocess.run(["git", "checkout", "-"], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "y"], cwd=git_repo, capture_output=True, check=True)
        out = _get_hidden_commits_for_date(git_repo, "2025-12-11", message_depth="subject", include_files=True)
        assert len(out) == 1
        assert "tracked_hidden.py" in out[0].files

    def test_sort_orders_by_date_then_hash(self, git_repo: Path) -> None:
        """The sort key (c.date, c.hash) must produce a deterministic ordering.
        key=None or key=lambda c: None would either crash or leave order undefined."""
        # Create three hidden commits on the same date so the secondary sort
        # by hash determines the order.
        _commit(git_repo, "v.py", "v", "feat: v", "2025-12-20")
        subprocess.run(["git", "checkout", "-b", "z"], cwd=git_repo, capture_output=True, check=True)
        _commit(git_repo, "h1.py", "1", "feat: h1", "2025-12-21")
        _commit(git_repo, "h2.py", "2", "feat: h2", "2025-12-21")
        _commit(git_repo, "h3.py", "3", "feat: h3", "2025-12-21")
        subprocess.run(["git", "checkout", "-"], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(["git", "branch", "-D", "z"], cwd=git_repo, capture_output=True, check=True)
        out = _get_hidden_commits_for_date(
            git_repo, "2025-12-21", message_depth="subject", include_files=False
        )
        assert len(out) == 3
        # Sorted by (date, hash) — since dates are equal, hashes must be ascending
        hashes = [c.hash for c in out]
        assert hashes == sorted(hashes)
