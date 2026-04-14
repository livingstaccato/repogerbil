from repogerbil.core.artifact_patterns import ARTIFACT_RULES, ArtifactRule


def _rule_for(path: str) -> ArtifactRule | None:
    for rule in ARTIFACT_RULES:
        if rule.matches(path):
            return rule
    return None  # pragma: no cover


class TestArtifactPatterns:
    def test_artifact_rule_creation(self) -> None:
        rule = ArtifactRule("test label", r"test_pattern", r"test_flag")
        assert rule.label == "test label"
        assert rule.pattern == r"test_pattern"
        assert rule.flag == r"test_flag"
        assert rule._compiled is not None

    def test_pycache_matches(self) -> None:
        assert _rule_for("src/foo/__pycache__/bar.cpython-313.pyc") is not None

    def test_pyc_extension(self) -> None:
        r = _rule_for("src/mod.pyc")
        assert r is not None and r.label == "Python bytecode"

    def test_lock_file(self) -> None:
        r = _rule_for("poetry.lock")
        assert r is not None and r.label == "lock file"

    def test_pipfile_lock(self) -> None:
        assert _rule_for("provider/hello-world/Pipfile.lock") is not None

    def test_claude_dir(self) -> None:
        r = _rule_for(".claude/settings.json")
        assert r is not None and r.label == "AI tool config"

    def test_claude_file_at_root(self) -> None:
        r = _rule_for(".claude")
        assert r is not None

    def test_dotclaude_not_false_positive(self) -> None:
        assert _rule_for("src/notclaude/file.py") is None

    def test_handoff_doc(self) -> None:
        assert _rule_for(".provide/HANDOFF.md") is not None

    def test_regular_source_file_no_match(self) -> None:
        assert _rule_for("src/repogerbil/core/snapshot.py") is None

    def test_build_dir(self) -> None:
        assert _rule_for("build/output.bin") is not None

    def test_no_false_positive_on_build_in_name(self) -> None:
        assert _rule_for("src/rebuild.py") is None
