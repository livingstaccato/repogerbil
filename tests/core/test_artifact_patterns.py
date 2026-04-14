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

    def test_artifact_rule_flag_defaults_to_pattern(self) -> None:
        rule = ArtifactRule("test label", r"test_pattern")
        assert rule.label == "test label"
        assert rule.pattern == r"test_pattern"
        assert rule.flag == r"test_pattern"
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

    def test_no_false_positive_on_git_lock_file(self) -> None:
        """Ensure .git/index.lock is not matched by the lock file pattern."""
        assert _rule_for(".git/index.lock") is None

    def test_htmlcov_pattern_anchored(self) -> None:
        """Ensure htmlcov/ is anchored at the start."""
        assert _rule_for("htmlcov/index.html") is not None
        assert _rule_for(".venv/lib/python3.11/site-packages/htmlcov/file.html") is None

    def test_mutation_testing_meta_file(self) -> None:
        r = _rule_for("mutants/src/pyvider/cty/codec.py.meta")
        assert r is not None and r.label == "mutation testing"

    def test_mutation_testing_dir(self) -> None:
        assert _rule_for("mutants/src/foo.py") is not None

    def test_bak_file(self) -> None:
        r = _rule_for("docs/MIGRATION.md.bak")
        assert r is not None and r.label == "backup file"

    def test_cov_xml(self) -> None:
        r = _rule_for("cov.xml")
        assert r is not None and r.label == "coverage report"

    def test_coverage_xml(self) -> None:
        assert _rule_for("coverage.xml") is not None

    def test_go_sum(self) -> None:
        r = _rule_for("go.sum")
        assert r is not None and r.label == "lock file"

    def test_go_sum_in_subdir(self) -> None:
        assert _rule_for("compatibility/go/go.sum") is not None

    def test_python_version_file(self) -> None:
        r = _rule_for(".python-version")
        assert r is not None and r.label == "tool config"

    def test_actrc(self) -> None:
        assert _rule_for(".actrc") is not None

    def test_pyre_configuration(self) -> None:
        assert _rule_for(".pyre_configuration") is not None

    def test_pyi_stub_file(self) -> None:
        r = _rule_for("pyvider/cty/codec.pyi")
        assert r is not None and r.label == "generated stub"

    def test_py_file_not_matched_by_pyi(self) -> None:
        assert _rule_for("src/module.py") is None

    def test_codeowners(self) -> None:
        r = _rule_for(".github/CODEOWNERS")
        assert r is not None and r.label == "VCS meta"

    def test_codeowners_at_root(self) -> None:
        assert _rule_for("CODEOWNERS") is not None

    def test_zip_archive(self) -> None:
        r = _rule_for("src/pyvider/cty.zip")
        assert r is not None and r.label == "build artifact"

    def test_vendor_dir(self) -> None:
        r = _rule_for("vendor/github.com/hashicorp/go-cty/cty.go")
        assert r is not None and r.label == "vendored dependency"

    def test_node_modules(self) -> None:
        assert _rule_for("node_modules/lodash/index.js") is not None

    def test_py_typed_not_matched(self) -> None:
        assert _rule_for("src/repogerbil/py.typed") is None
