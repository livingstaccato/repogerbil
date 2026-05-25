# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for changelog enrichment."""

from pathlib import Path
import subprocess

import pytest
import yaml

from repogerbil.core.enrich import _run_file_shortstat, enrich_changelog
from repogerbil.core.errors import GitCommandError


def _init_enrich_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("import utils\nprint('hello')\n")
    (repo / "src" / "utils.py").write_text("def helper(): pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )
    (repo / "src" / "main.py").write_text("import utils\nprint('updated')\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: update main"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
    )
    return repo


class TestEnrichChangelog:
    def test_adds_section_stats(self, tmp_path: Path) -> None:
        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"commits": 2, "files_changed": 2, "insertions": 3, "deletions": 1},
                    "changes": [
                        {
                            "title": "Update main",
                            "category": "remediate",
                            "severity": "behavioral",
                            "files": [{"path": "src/main.py", "summary": "Updated"}],
                            "points": [{"text": "fix", "files": ["src/main.py"]}],
                        }
                    ],
                }
            )
        )
        result = enrich_changelog(yaml_path, repo, depth="file")
        assert result is True
        data = yaml.safe_load(yaml_path.read_text())
        assert "stats" in data["changes"][0]

    def test_no_changes(self, tmp_path: Path) -> None:
        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "empty.yaml"
        yaml_path.write_text(yaml.dump({"date": "2026-04-07", "repo": "repo", "changes": []}))
        assert enrich_changelog(yaml_path, repo) is False

    def test_no_data(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("not a dict")
        assert enrich_changelog(yaml_path, tmp_path) is False

    def test_no_date(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "nodate.yaml"
        yaml_path.write_text(yaml.dump({"repo": "x", "changes": [{"title": "t", "files": [{"path": "f"}]}]}))
        assert enrich_changelog(yaml_path, tmp_path) is False

    def test_no_commits(self, tmp_path: Path) -> None:
        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "nocommits.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2020-01-01",
                    "repo": "repo",
                    "changes": [{"title": "t", "files": [{"path": "f.py"}]}],
                }
            )
        )
        assert enrich_changelog(yaml_path, repo) is False

    def test_section_without_files(self, tmp_path: Path) -> None:
        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "nofiles.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "changes": [{"title": "t", "points": []}],
                }
            )
        )
        assert enrich_changelog(yaml_path, repo) is False

    def test_impact_not_attached_when_find_importers_returns_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _find_importers returns {}, change must not gain an 'impact' key."""
        from repogerbil.core import enrich as enrich_mod

        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "empty_impact.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "changes": [
                        {
                            "title": "Work",
                            "files": [{"path": "src/main.py"}],
                            "points": [{"text": "fix", "files": ["src/main.py"]}],
                        }
                    ],
                }
            )
        )
        monkeypatch.setattr(enrich_mod, "_find_importers", lambda *_a, **_kw: {})
        enrich_changelog(yaml_path, repo, depth="file")
        data = yaml.safe_load(yaml_path.read_text())
        assert "impact" not in data["changes"][0]

    def test_impact_attached_when_find_importers_returns_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _find_importers returns non-empty, change gains an 'impact' key."""
        from repogerbil.core import enrich as enrich_mod

        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "with_impact.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "changes": [
                        {
                            "title": "Work",
                            "files": [{"path": "src/main.py"}],
                            "points": [{"text": "fix", "files": ["src/main.py"]}],
                        }
                    ],
                }
            )
        )
        monkeypatch.setattr(enrich_mod, "_find_importers", lambda *_a, **_kw: {"files": ["src/other.py"]})
        enrich_changelog(yaml_path, repo, depth="file")
        data = yaml.safe_load(yaml_path.read_text())
        assert data["changes"][0]["impact"] == {"files": ["src/other.py"]}

    def test_package_depth(self, tmp_path: Path) -> None:
        repo = _init_enrich_repo(tmp_path)
        yaml_path = tmp_path / "pkg.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "changes": [
                        {
                            "title": "Work",
                            "files": [{"path": "src/main.py"}],
                            "points": [{"text": "fix", "files": ["src/main.py"]}],
                        }
                    ],
                }
            )
        )
        enrich_changelog(yaml_path, repo, depth="package")
        data = yaml.safe_load(yaml_path.read_text())
        change = data["changes"][0]
        assert "stats" in change or "impact" in change

    def test_single_commit_day_enriches_stats(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo_single"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (repo / "src").mkdir()
        (repo / "src" / "only.py").write_text("print('x')\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: only"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-08T10:00:00", "GIT_COMMITTER_DATE": "2026-04-08T10:00:00"},
        )

        yaml_path = tmp_path / "single.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-08",
                    "repo": "repo_single",
                    "changes": [{"title": "only", "files": [{"path": "src/only.py"}], "points": []}],
                }
            )
        )
        assert enrich_changelog(yaml_path, repo, depth="file") is True
        data = yaml.safe_load(yaml_path.read_text())
        assert data["changes"][0]["stats"]["files_changed"] == 1


class TestFindImporters:
    """Tests for ``_find_importers`` (depth-based git grep)."""

    def test_finds_importers_from_grep_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import enrich as enrich_mod

        # Mocked git grep returns two importing files; one is the changed file
        # itself (must be excluded) and one ends with .md (must be excluded).
        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            return "HEAD:src/consumer.py\nHEAD:src/utils.py\nHEAD:docs/notes.md\n"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="file")
        assert impact["files"] == ["src/consumer.py"]
        assert "packages" not in impact  # file depth doesn't compute packages

    def test_package_depth_groups_by_parent_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import enrich as enrich_mod

        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            return "HEAD:pkg_a/x.py\nHEAD:pkg_b/y.py\n"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="package")
        assert impact["files"] == ["pkg_a/x.py", "pkg_b/y.py"]
        assert impact["packages"] == ["pkg_a/", "pkg_b/"]

    def test_grep_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """git grep exits 1 when there are no matches — must not propagate."""
        from repogerbil.core import enrich as enrich_mod

        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            raise GitCommandError("no matches", returncode=1, stderr="")

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="file")
        # No matches → no "files" key, no "packages" key.
        assert impact == {}

    def test_cross_repo_depth_also_computes_packages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import enrich as enrich_mod

        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            return "HEAD:pkg_a/x.py\n"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="cross-repo")
        assert impact["files"] == ["pkg_a/x.py"]
        assert impact["packages"] == ["pkg_a/"]

    def test_root_level_importer_is_excluded_from_packages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A root-level file gives parent './' which is filtered out of packages."""
        from repogerbil.core import enrich as enrich_mod

        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            return "HEAD:top.py\n"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="package")
        assert impact["files"] == ["top.py"]
        # Parent of "top.py" is "." → "./" which the function deliberately excludes.
        assert "packages" not in impact

    def test_grep_line_without_colon_is_kept_verbatim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines without a ``:`` separator should be used as the path directly."""
        from repogerbil.core import enrich as enrich_mod

        def fake_run_git(repo_path: object, *args: object, timeout: int = 60) -> str:
            return "src/bare.py\n"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        impact = enrich_mod._find_importers(Path(), {"src/utils.py"}, depth="file")
        assert impact["files"] == ["src/bare.py"]


class TestRunFileShortstat:
    def test_falls_back_to_root_on_missing_parent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import enrich as enrich_mod

        calls: list[tuple[str, ...]] = []

        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            calls.append(args)
            if "^.." in args[2]:
                raise GitCommandError("no parent", returncode=128)
            return " 1 file changed, 1 insertion(+)"

        monkeypatch.setattr(enrich_mod, "_run_git", fake_run_git)
        out = _run_file_shortstat(Path(), "a" * 40, "a" * 40, {"a.py"})
        assert "file changed" in out
        assert "--root" in calls[1]
