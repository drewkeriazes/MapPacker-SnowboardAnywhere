"""Shared test helpers. The game is a separate repo now (FEAT-238): tests that compare with a game file read it from
the SnowboardAnywhere checkout next to this one (pipeline/paths.py: SBA_GAME_REPO overrides) and skip without it.

Those tests are marked `game` (FEAT-240): CI's format-check job runs them with `-m game` against a checkout of the
game's main, and SBA_REQUIRE_GAME=1 turns a missing game file into a failure there instead of a skip."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "game: compares with a file in the SnowboardAnywhere checkout (the game_file fixture)")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "game_file" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.game)


@pytest.fixture
def game_file():
    """game_file("game", "src", ...) -> the path in the game checkout; skips the test when the file is not there"""
    def get(*parts):
        p = os.path.join(paths.game_repo(), *parts)
        if not os.path.isfile(p):
            msg = f"no {'/'.join(parts)}: no SnowboardAnywhere checkout at {paths.game_repo()} (SBA_GAME_REPO)"
            if os.environ.get("SBA_REQUIRE_GAME") == "1":
                pytest.fail(msg)
            pytest.skip(msg)
        return p
    return get
