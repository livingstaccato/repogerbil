# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Compatibility re-exports for legacy append module names."""

from repogerbil.core import catch_up as _catch_up

AppendResult = _catch_up.AppendResult
CatchUpResult = _catch_up.CatchUpResult
_attach_files = _catch_up._attach_files
_commit_signature = _catch_up._commit_signature
_read_signatures_for_date = _catch_up._read_signatures_for_date
_record_signature = _catch_up._record_signature
_scan_head_commits = _catch_up._scan_head_commits
append_new_commits = _catch_up.append_new_commits
build_record = _catch_up.build_record
count_jsonl_entries = _catch_up.count_jsonl_entries
read_latest_date = _catch_up.read_latest_date
read_recorded_hashes = _catch_up.read_recorded_hashes
record_missing_commits = _catch_up.record_missing_commits
