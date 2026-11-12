"""FEAT-238: where the pipeline reads and writes in MapPacker, and how it finds the game."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths  # noqa: E402
from publish_pack import resort_files  # noqa: E402


def test_layout_is_at_the_repo_root():
    assert paths.RESORTS == os.path.join(paths.REPO, "resorts") and os.path.isfile(paths.config_path("vail"))
    assert paths.config_path("vail") == os.path.join(paths.REPO, "resorts", "vail", "vail.json")
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
    for f in ("resorts/demo/demo.json", "resorts/demo/demo-plan.md", "resorts/demo/demo_ept_nodes.txt",
              "resorts/demo/demo_ept_far_nodes.txt", "manifests/demo.json", "reports/demo.md",
              "resorts/demox/demox.json", "resorts/other/other_ept_nodes.txt", "resorts/demo.json"):
        os.makedirs(tmp_path / os.path.dirname(f), exist_ok=True)
        (tmp_path / f).write_text("x")
    assert resort_files("demo", str(tmp_path)) == ["resorts/demo/demo.json", "resorts/demo/demo-plan.md",
                                                   "manifests/demo.json", "reports/demo.md",
                                                   "resorts/demo/demo_ept_far_nodes.txt",
                                                   "resorts/demo/demo_ept_nodes.txt"]   # not a stray flat resorts/demo.json


def test_every_resort_has_its_own_folder_with_the_node_lists_it_names():
    """FEAT-244: resorts/<slug>/ holds the config and every nodes_file it names; nothing is left flat in resorts/"""
    flat = [f for f in os.listdir(paths.RESORTS) if os.path.isfile(os.path.join(paths.RESORTS, f))]
    assert flat == []
    slugs = sorted(d for d in os.listdir(paths.RESORTS) if os.path.isdir(paths.resort_dir(d)))
    assert "vail" in slugs
    for slug in slugs:
        cfg = json.load(open(paths.config_path(slug), encoding="utf-8"))
        assert cfg["slug"] == slug
        L = cfg.get("lidar") or {}
        for src in [L] + list(L.get("extra", [])) + [L.get("far") or {}]:
            if src.get("nodes_file"):     # FEAT-268: a raw_from config's lists are that resort's
                home = paths.resort_dir(cfg.get("raw_from") or slug)
                assert os.path.isfile(os.path.join(home, src["nodes_file"])), (slug, src["nodes_file"])
