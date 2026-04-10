# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for new git functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from repogerbil.core.git import (
    get_active_dates,
    get_commits_for_date,
    get_diff_stats,
    parse_shortstat,
)


def test_parse_shortstat() -> None:
    """parse_shortstat should correctly extract numbers."""
    stat = " 3 files changed, 10 insertions(+), 5 deletions(-)"
    res = parse_shortstat(stat)
    assert res["files_changed"] == 3
    assert res["insertions"] == 10
    assert res["deletions"] == 5

    assert parse_shortstat("") == {"files_changed": 0, "insertions": 0, "deletions": 0}


def test_get_diff_stats_fallback() -> None:
    """get_diff_stats should use --root for first commit."""
    with patch("subprocess.run") as mock_run:
        # First call fails (empty), second call succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="\n"),
            MagicMock(returncode=0, stdout=" 1 file changed, 1 insertion(+)"),
        ]
        res = get_diff_stats(".", "hash1", "hash2")
        assert res.files_changed == 1
        assert mock_run.call_count == 2


def test_get_commits_with_body() -> None:
    """get_commits_for_date should parse full message with bodies."""
    h1 = "a" * 40
    h2 = "b" * 40
    output = (
        f"{h1}\x002026-04-10\x00feat: test\x00This is the body\nFixes #123\x00END"
        f"{h2}\x002026-04-10\x00fix: other\x00\x00END"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=output)
        commits = get_commits_for_date(".", "2026-04-10", message_depth="full")
        assert len(commits) == 2
        # Note: get_commits_for_date calls reverse()
        assert commits[1].body == "This is the body\nFixes #123"
        assert commits[1].refs == ["#123"]
        assert commits[0].body == ""


def test_get_commits_subject_only() -> None:
    """get_commits_for_date should parse subject-only format."""
    h1 = "a" * 40
    h2 = "b" * 40
    # Two commits, but only h1 matches the date 2026-04-10
    output = f"{h1}\t2026-04-10\tfeat: test\n{h2}\t2026-04-11\tfix: other\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=output)
        commits = get_commits_for_date(".", "2026-04-10", message_depth="subject")
        assert len(commits) == 1
        assert commits[0].subject == "feat: test"


def test_attach_file_lists() -> None:
    """get_commits_for_date should attach file lists when requested."""
    h1 = "a" * 40
    log_output = f"{h1}\t2026-04-10\tfeat: test\n"
    files_output = f"{h1}\nfile1.py\nfile2.py\n"
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=log_output),
            MagicMock(returncode=0, stdout=files_output),
        ]
        commits = get_commits_for_date(".", "2026-04-10", include_files=True)
        assert len(commits) == 1
        assert commits[0].files == ["file1.py", "file2.py"]


def test_get_active_dates_empty() -> None:
    """get_active_dates should return an empty set if no output."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="\n")
        assert get_active_dates(".") == set()


def test_get_commits_subject_only_empty() -> None:
    """_parse_commits_subject_only with empty output."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert get_commits_for_date(".", "2026-04-10") == []


def test_get_diff_stats_empty() -> None:
    """get_diff_stats with empty output."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="\n")
        res = get_diff_stats(".", "h1", "h2")
        assert res.commits == 0
        assert res.files_changed == 0


def test_attach_file_lists_edge_cases() -> None:
    """_attach_file_lists edge cases: empty lines and non-hash lines."""
    from repogerbil.core.git import CommitInfo, _attach_file_lists

    h1 = "a" * 40
    # Output with empty line and non-hash leading line (though unlikely in git)
    output = f"\n{h1}\nfile1.py\n\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=output)
        commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test")]
        res = _attach_file_lists(".", commits)
        assert res[0].files == ["file1.py"]


def test_get_commits_for_date_no_commits() -> None:
    """get_commits_for_date should return an empty list if no commits found."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="\n")
        assert get_commits_for_date(".", "2026-04-10") == []
