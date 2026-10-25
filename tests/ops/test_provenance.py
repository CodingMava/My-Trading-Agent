"""What processed a run: the commit from .git (branch, packed or detached) and digests of the source and configuration."""
from trader.ops.provenance import commit, provenance


def test_a_run_names_its_commit_and_the_exact_source_and_configuration(tmp_path):
    (tmp_path / "trader" / "__pycache__").mkdir(parents=True)
    (tmp_path / "trader" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "trader" / "__pycache__" / "a.py").write_text("cached\n", encoding="utf-8")  # never counted
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "settings.toml").write_text("[live]\nenabled = false\n", encoding="utf-8")
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("0123456789abcdef0123\n", encoding="utf-8")
    code, config = provenance(tmp_path)
    assert code.startswith("0123456789ab src ") and len(config) == 16
    (tmp_path / "trader" / "__pycache__" / "a.py").write_text("changed\n", encoding="utf-8")
    assert provenance(tmp_path) == (code, config)
    (tmp_path / "trader" / "a.py").write_text("x = 2\n", encoding="utf-8")  # an uncommitted change shows
    changed = provenance(tmp_path)
    assert changed[0] != code and changed[0].startswith("0123456789ab src ") and changed[1] == config
    (tmp_path / "config" / "settings.toml").write_text("[live]\nenabled = true\n", encoding="utf-8")
    assert provenance(tmp_path)[1] != config
    (git / "refs" / "heads" / "main").unlink()
    (git / "packed-refs").write_text("# pack-refs with: peeled\nfedcba9876543210 refs/heads/main\n", encoding="utf-8")
    assert commit(tmp_path) == "fedcba9876543210"
    (git / "packed-refs").write_text("fedcba9876543210 refs/heads/other\n", encoding="utf-8")
    assert commit(tmp_path) == ""  # the branch isn't anywhere
    (git / "HEAD").write_text("abcdef1234\n", encoding="utf-8")  # detached
    assert commit(tmp_path) == "abcdef1234"
    assert commit(tmp_path / "nowhere") == "" and provenance(tmp_path / "nowhere")[0].startswith("unknown src ")
