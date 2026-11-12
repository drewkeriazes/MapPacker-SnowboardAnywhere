"""FEAT-238: where the pipeline reads and writes in MapPacker, and how it finds the game."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths  # noqa: E402
from publish_pack import ready_to_commit, resort_files  # noqa: E402


def test_layout_is_at_the_repo_root():
    assert paths.RESORTS == os.path.join(paths.REPO, "resorts") and os.path.isfile(os.path.join(paths.RESORTS, "vail.json"))
    assert paths.MANIFESTS == os.path.join(paths.REPO, "manifests")
    assert paths.PACKS == os.path.join(paths.REPO, "packs")
    assert os.path.isfile(os.path.join(paths.REPO, "catalog.json"))


def test_raw_root_is_sba_raw_root_else_the_main_checkouts_raw(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_RAW_ROOT", raising=False)
    main = paths.main_checkout()
    assert os.path.exists(os.path.join(main, ".git")) and paths.raw_root() == os.path.join(main, "raw")
    monkeypatch.setenv("SBA_RAW_ROOT", str(tmp_path))
    assert paths.raw_root() == str(tmp_path)


def test_game_repo_is_the_override_else_sba_game_repo_else_the_sibling(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_GAME_REPO", raising=False)
    assert paths.game_repo() == os.path.join(os.path.dirname(paths.main_checkout()), "SnowboardAnywhere")
    monkeypatch.setenv("SBA_GAME_REPO", str(tmp_path / "env"))
    assert paths.game_repo() == str(tmp_path / "env")
    assert paths.game_repo(str(tmp_path / "arg")) == str(tmp_path / "arg")


def test_require_game_says_where_it_looked(tmp_path):
    with pytest.raises(SystemExit, match=r"the ride stage needs the game: no SnowboardAnywhere checkout at .*nowhere"):
        paths.require_game("the ride stage", str(tmp_path / "nowhere"))
    (tmp_path / "sba" / "game").mkdir(parents=True)
    (tmp_path / "sba" / "game" / "package.json").write_text("{}")
    assert paths.require_game("x", str(tmp_path / "sba")) == str(tmp_path / "sba")


def test_publish_commits_the_resorts_own_files(tmp_path):
    for f in ("resorts/demo.json", "resorts/demo-plan.md", "resorts/demo_ept_nodes.txt", "resorts/demo_ept_far_nodes.txt",
              "manifests/demo.json", "reports/demo.md", "resorts/demox.json", "resorts/other_ept_nodes.txt"):
        os.makedirs(tmp_path / os.path.dirname(f), exist_ok=True)
        (tmp_path / f).write_text("x")
    assert resort_files("demo", str(tmp_path)) == ["resorts/demo.json", "resorts/demo-plan.md", "manifests/demo.json",
                                                   "reports/demo.md", "resorts/demo_ept_far_nodes.txt",
                                                   "resorts/demo_ept_nodes.txt"]


def git(repo, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


def test_publish_refuses_a_checkout_not_on_main(tmp_path):
    git(tmp_path, "init", "-q", "-b", "card")
    (tmp_path / "catalog.json").write_text(json.dumps({"resorts": []}))
    git(tmp_path, "add", "catalog.json")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x")
    with pytest.raises(SystemExit, match="is on card: publish from the main checkout on main"):
        ready_to_commit(str(tmp_path))
