"""Shared test helpers. The game is a separate repo now (FEAT-238): tests that compare with a game file read it from
the SnowboardAnywhere checkout next to this one (pipeline/paths.py: SBA_GAME_REPO overrides) and skip without it."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths  # noqa: E402


@pytest.fixture
def game_file():
    """game_file("game", "src", ...) -> the path in the game checkout; skips the test when the file is not there"""
    def get(*parts):
        p = os.path.join(paths.game_repo(), *parts)
        if not os.path.isfile(p):
            pytest.skip(f"no {'/'.join(parts)}: no SnowboardAnywhere checkout at {paths.game_repo()} (SBA_GAME_REPO)")
        return p
    return get
