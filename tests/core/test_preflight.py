from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

from repogerbil.core.preflight import PreflightReport, _count_files, scan_repo


def _make_repo(tmp_path: Path) -> Path:
    """Minimal repo with source, artifact, and unknown files."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)

    # Commit 1: initial source
    (repo / "main.py").write_text("x = 1\n")
    (repo / "README.md").write_text("# Readme\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)

    # Commit 2: add artifacts + unknown
    pycache = repo / "__pycache__"
    pycache.mkdir()
    (pycache / "main.cpython-313.pyc").write_bytes(b"\x00\x01\x02")
    (repo / "poetry.lock").write_text("lock\n")
    (repo / "mystery.bin").write_bytes(b"\xde\xad\xbe\xef")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add files"], cwd=repo, capture_output=True, check=True)

    # Commit 3: touch main.py again (count > 1)
    (repo / "main.py").write_text("x = 2\n")
    subprocess.run(["git", "add", "main.py"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "update"], cwd=repo, capture_output=True, check=True)

    return repo


class TestScanRepo:
    def test_artifacts_detected(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        artifact_paths = {r.path for r in report.artifacts}
        assert any("__pycache__" in p for p in artifact_paths)
        assert any("poetry.lock" in p for p in artifact_paths)

    def test_source_files_bucketed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        source_paths = {r.path for r in report.source}
        assert "main.py" in source_paths
        assert "README.md" in source_paths

    def test_unknown_files_bucketed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        unknown_paths = {r.path for r in report.unknown}
        assert "mystery.bin" in unknown_paths

    def test_commit_counts(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        main_record = next(r for r in report.source if r.path == "main.py")
        assert main_record.commit_count == 2

    def test_suggested_flags_not_empty(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        assert len(report.suggested_flags) > 0

    def test_suggested_flags_no_duplicates(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        assert len(report.suggested_flags) == len(set(report.suggested_flags))

    def test_returns_preflight_report_type(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        assert isinstance(scan_repo(repo), PreflightReport)

    def test_since_filter(self, tmp_path: Path) -> None:
        """since parameter is passed through to git log."""
        repo = _make_repo(tmp_path)
        # A future date means no commits match; should return empty report.
        report = scan_repo(repo, since="2099-01-01")
        assert report.artifacts == ()
        assert report.source == ()
        assert report.unknown == ()
        assert report.suggested_flags == ()

    def test_until_filter(self, tmp_path: Path) -> None:
        """until parameter is passed through to git log."""
        repo = _make_repo(tmp_path)
        # A past date means no commits match; should return empty report.
        report = scan_repo(repo, until="1970-01-01")
        assert report.artifacts == ()
        assert report.source == ()
        assert report.unknown == ()
        assert report.suggested_flags == ()

    def test_file_record_rule_is_none_for_source(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        main_record = next(r for r in report.source if r.path == "main.py")
        assert main_record.rule is None

    def test_file_record_rule_set_for_artifacts(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        report = scan_repo(repo)
        lock_record = next(r for r in report.artifacts if "poetry.lock" in r.path)
        assert lock_record.rule is not None
        assert lock_record.rule.label == "lock file"

    def test_source_filename_no_extension(self, tmp_path: Path) -> None:
        """Files in _SOURCE_FILENAMES with no extension are classified as source."""
        repo = tmp_path / "repo2"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True)
        (repo / "Makefile").write_text("all:\n\techo done\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add Makefile"], cwd=repo, capture_output=True, check=True)

        report = scan_repo(repo)
        source_paths = {r.path for r in report.source}
        assert "Makefile" in source_paths


class TestCountFiles:
    def test_blank_lines_skipped(self, tmp_path: Path) -> None:
        """Blank lines emitted by git --format= between commits are ignored."""
        mock_result = MagicMock()
        mock_result.stdout = "\nmain.py\n\nREADME.md\n\n"
        with patch("repogerbil.core.preflight.subprocess.run", return_value=mock_result):
            counts = _count_files(tmp_path, None, None)
        assert counts["main.py"] == 1
        assert counts["README.md"] == 1
        assert "" not in counts
