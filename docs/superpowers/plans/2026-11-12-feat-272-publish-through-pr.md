# FEAT-272 Publish Through a Pull Request: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pack publish arrives as a pull request that a workflow releases and merges, so nothing pushes to `main`.

**Architecture:** `publish_pack.py` uploads a draft release and opens a `publish/<slug>-v<N>` PR from a throwaway worktree. A `publish-check` job in Checks downloads the draft zip and lints it with scripts from `main`. `publish-merge.yml` (driven by `pipeline/publish_merge.py`, pure decision logic plus thin `gh` calls) checks label provenance and the file set, publishes the draft, then merges with a GitHub App token. The ride leaves the default `resort.py add` flow.

**Tech Stack:** Python 3.13 (pytest, numpy, Pillow already in `pipeline/requirements.txt`), `gh` CLI, GitHub Actions (`actions/create-github-app-token`), GitHub rulesets API.

**Spec:** `docs/superpowers/specs/2026-11-12-publish-through-pr-design.md`

## Global Constraints

- Nothing pushes to `main`, in code or in any step of this plan. No bypass of the ruleset of any kind (the spec's anti-goals).
- Release tags stay `<slug>-v<N>` in this card; FEAT-271 renames them later.
- Publish branch name: `publish/<slug>-v<N>`. Labels: `publish`, `automerge`, `accept-change`.
- Publish file set (the only paths a publish PR may change): `catalog.json`, `RELEASES.md`, `reports/<slug>.md`, `resorts/<slug>/**`, `manifests/<slug>.json`.
- Size ceilings: `MAX_PACK_BYTES = 600_000_000`, `MAX_FILES = 5_000`, `MAX_TREES_PER_KM2 = 80_000` (about twice today's largest: Vail 287 MB, 2,135 files, 39,201 per km²).
- Maintainers list: `.github/maintainers.txt`, one GitHub login per line, `#` comments; today one line, `drewkeriazes`.
- GitHub App secrets: `PUBLISH_APP_ID`, `PUBLISH_APP_KEY`.
- Check scripts that hold a write token run from `main`'s copy of `pipeline/`, never the PR's.
- Commits: plain message with the card id (`FEAT-272: ...`), no `Co-Authored-By`, authored as Drew. No em dashes in Markdown (repo-rules).
- `python -m pytest pipeline/tests` passes after every task. Pushes from this branch use `SA_SKIP_GPU_BUDGETS=1` (nothing here changes what the game draws).

## Review Focus

1. **Two publishes in flight for different resorts.** The second PR's `catalog.json` conflicts once the first merges; it must be refreshed and merge, not hang. Test: `test_rebase_catalog_keeps_both_resorts` (Task 5).
2. **A label added by someone not in the maintainers list.** No release, no merge. Test: `test_label_from_a_non_maintainer_is_refused` (Task 5).
3. **A `publish` PR that also changes code.** Never merges itself, and the Claude reviewer still reviews it. Tests: `test_files_outside_the_publish_set_are_refused` (Task 5), `test_review_runs_on_a_publish_pr_with_code` (Task 6).
4. **A pack built from uncommitted or unmerged pipeline code, or with no stamp** (Big Sky, Breckenridge today). Refused before anything is uploaded, with the rebuild command. Tests: `test_stamp_problem_*` (Task 2).
5. **Someone merges a publish PR with the merge button.** The draft is published within seconds by the `closed` handler. Test: `test_merged_pr_with_a_draft_publishes_it` (Task 5).

---

### Task 1: Pack lint

**Files:**
- Create: `pipeline/pack_lint.py`
- Test: `pipeline/tests/test_pack_lint.py`

**Interfaces:**
- Produces: `lint(pack_dir: str) -> list[str]` (problems, empty when clean); `lint_zip(zip_path: str) -> list[str]` (extracts to a temp dir, then `lint`); constants `MAX_PACK_BYTES`, `MAX_FILES`, `MAX_TREES_PER_KM2`, `TILE_SETS = ("terrain.fine", "terrain.coarse", "terrain.mid", "terrain.far", "mask", "ao", "dir", "moguls")`, `RECORD_BYTES = 24`. CLI: `python pipeline/pack_lint.py <pack_dir or .zip>` prints problems, exit 1 if any.

What it checks, from `meta.json`:
- `formatVersion == packwriter.FORMAT_VERSION`.
- Each tile set in `TILE_SETS` present in meta: every `<set dir>/<tx>_<ty>.png` for `tx < tilesX`, `ty < tilesY` exists, decodes with Pillow, and all tiles in a set have one size. The set dir is the last part of the key (`terrain.fine` -> `fine/`).
- Instance files `trees/`, `shrubs/`, `rocks/`, `farTrees/`: each `<cell>.bin` named in `instances.treeCells` / `shrubCells` / `rockCells` / `farTreeCells` exists and its size is a multiple of `RECORD_BYTES`.
- `stands/<cell>.png` for each of `stands.cells`, decodes.
- `features.json` parses and has list `runs` and list `lifts`.
- `report.json`, when present, has `build == meta["build"]`.
- Ceilings: total bytes (all files but `debug/`) <= `MAX_PACK_BYTES`; file count <= `MAX_FILES`; `(instances.treeCount + stands.stems) / area_km2 <= MAX_TREES_PER_KM2` with area from `bounds`.

- [ ] **Step 1: Write the failing tests** in `test_pack_lint.py` with a helper `tiny_pack(tmp_path) -> str` that writes a 1x1-tile pack (each tile set one 4x4 PNG, one tree cell with 2 records = 48 bytes, one stand cell PNG, `features.json` with one run and one lift, `report.json` with the meta's build, `formatVersion = FORMAT_VERSION`, bounds 1000 x 1000 m).

```python
def test_a_clean_pack_has_no_problems(tmp_path):
    assert lint(tiny_pack(tmp_path)) == []

def test_a_missing_tile_is_named(tmp_path):
    p = tiny_pack(tmp_path); os.remove(os.path.join(p, "mask", "0_0.png"))
    assert any("mask/0_0.png" in x for x in lint(p))

def test_a_truncated_instance_file_is_named(tmp_path):
    p = tiny_pack(tmp_path)
    with open(os.path.join(p, "trees", "0_0.bin"), "ab") as f: f.write(b"\0" * 5)
    assert any("trees/0_0.bin" in x and "24" in x for x in lint(p))

def test_a_report_for_another_build_is_named(tmp_path):
    p = tiny_pack(tmp_path); write_json(os.path.join(p, "report.json"), {"build": "other"})
    assert any("report.json" in x for x in lint(p))

def test_wrong_format_version_is_named(tmp_path):
    p = tiny_pack(tmp_path, format_version=FORMAT_VERSION + 1)
    assert any("formatVersion" in x for x in lint(p))

def test_tree_density_over_the_ceiling_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(pack_lint, "MAX_TREES_PER_KM2", 1)
    assert any("per km2" in x for x in lint(tiny_pack(tmp_path)))

def test_lint_zip_reads_a_published_zip(tmp_path):
    p = tiny_pack(tmp_path); z = str(tmp_path / "p.zip"); publish_pack.zip_pack(p, z)
    assert lint_zip(z) == []
```

- [ ] **Step 2: Run them to see them fail.** `python -m pytest pipeline/tests/test_pack_lint.py -v`. Expected: FAIL, `No module named 'pack_lint'`.
- [ ] **Step 3: Implement `pipeline/pack_lint.py`** with the interfaces above.
- [ ] **Step 4: Run the tests.** Same command. Expected: 7 passed.
- [ ] **Step 5: Lint the real packs.** `for p in packs/*/; do python pipeline/pack_lint.py "$p"; done` in the main checkout. Expected: no problems for vail, park-city-mountain, boston-mills, ohio-hills, synth. Investigate anything else before going on (a real problem in a published pack becomes its own card; a lint mistake gets fixed here).
- [ ] **Step 6: Commit.** `git add pipeline/pack_lint.py pipeline/tests/test_pack_lint.py && git commit -m "FEAT-272: pack_lint.py checks a pack's files against meta.json and the size ceilings"`

---

### Task 2: `publish_pack.py` opens a publish PR with a draft release

**Files:**
- Modify: `pipeline/publish_pack.py` (replace `ready_to_commit` and the commit/push block at `:259-309`; docstring steps 3 and 4)
- Create: `.github/maintainers.txt`
- Test: `pipeline/tests/test_publish_pack.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 3, 5, 6):
  - `stamp_problem(meta: dict, on_origin_main: Callable[[str], bool]) -> str | None`: `None` when `meta["pipeline"]` is set, has no `+dirty`, and `on_origin_main(sha)` is true; otherwise a message ending with the rebuild command `python pipeline/build_resort.py <slug> --force build`.
  - `maintainers(repo_dir: str = REPO) -> set[str]`.
  - `publisher_login() -> str`: `$GITHUB_TRIGGERING_ACTOR` when set (a workflow), else `gh api user --jq .login`.
  - `publish_branch(slug: str, version: int) -> str` returns `f"publish/{slug}-v{version}"`.
  - `pr_body(entry: dict, *, why: str, release_url: str, started_by: str, run_url: str | None, requested_by: str | None) -> str`: Markdown with the status and `why`, version, size, sha256, the draft link, `Started by: <login>`, `Run: <run_url>` when given, `Requested by: <requested_by>` when given, `Build: <meta build>`, and the line "Approve with the `automerge` label, not the merge button."
  - `open_publish_pr(*, slug: str, version: int, entry: dict, test: bool, src_repo: str, labels: list[str], body: str, repo: str) -> str`: returns the PR URL.
  - New flags: `--requested-by`, `--run-url`, `--accept-change` (adds the `accept-change` label).
- The catalog entry's `pack.pipeline` becomes `meta["pipeline"]` (the build stamp), not the publisher's `HEAD`.
- `next_version` keeps its logic; its tag list comes from `gh release list --json tagName` with drafts included (already the case; add the test so it stays so).

`open_publish_pr` steps, all with `run()`:
1. `git fetch origin main`; `git worktree add --detach <tmp> origin/main`.
2. In the worktree: write `catalog.json` as `update_catalog(<worktree catalog>, entry, test=test)`; copy the resort's files (`resort_files(slug, src_repo)`, plus the report) from `src_repo` to the same paths.
3. `git switch -c <publish_branch>`; `git add` exactly those paths; `git commit -m "<slug> v<N>: <status>, <MB> MB, pipeline <stamp>"`.
4. `git push -u origin <publish_branch>`; `gh pr create --base main --head <branch> --title "<slug> v<N>: publish" --body-file <tmp file> --label publish [...labels]`.
5. `git worktree remove --force <tmp>` in a `finally`.

`main()` order: format check, `stamp_problem` (refuse), status, version, zip, `gh release create <tag> --draft ...`, `open_publish_pr` with `automerge` when `publisher_login() in maintainers()`, print the PR URL. `--dry-run` prints the entry and the branch name and touches nothing.

- [ ] **Step 1: Create the three labels** (once, on GitHub): `gh label create publish --color 0E8A16 --description "FEAT-272: a pack publish"`, `gh label create automerge --color 1D76DB --description "FEAT-272: release and merge once checks pass"`, `gh label create accept-change --color FBCA04 --description "FEAT-264: a big change from the previous version is intended"`. Expected: three labels listed by `gh label list`.
- [ ] **Step 2: Write the failing tests** in `test_publish_pack.py`:

```python
def test_stamp_problem_accepts_a_clean_stamp_on_main():
    assert publish_pack.stamp_problem({"slug": "demo", "pipeline": "abc1234"}, lambda s: True) is None

def test_stamp_problem_refuses_a_missing_stamp():
    msg = publish_pack.stamp_problem({"slug": "bigsky"}, lambda s: True)
    assert "no pipeline stamp" in msg and "build_resort.py bigsky --force build" in msg

def test_stamp_problem_refuses_dirty_and_unmerged():
    assert "+dirty" in publish_pack.stamp_problem({"slug": "d", "pipeline": "abc1234+dirty"}, lambda s: True)
    assert "not on origin/main" in publish_pack.stamp_problem({"slug": "d", "pipeline": "abc1234"}, lambda s: False)

def test_next_version_counts_draft_tags():
    assert publish_pack.next_version("vail", ["vail-v3", "vail-v4"], {"resorts": []}) == 5

def test_maintainers_ignores_comments_and_blanks(tmp_path):
    (tmp_path / ".github").mkdir(); (tmp_path / ".github" / "maintainers.txt").write_text("# who\ndrewkeriazes\n\n")
    assert publish_pack.maintainers(str(tmp_path)) == {"drewkeriazes"}

def test_pr_body_names_the_requester_and_the_build():
    body = publish_pack.pr_body(ENTRY, why="report passes", release_url="u", started_by="drewkeriazes",
                                run_url="https://github.com/o/r/actions/runs/42", requested_by="player-1-id")
    assert "Requested by: player-1-id" in body and "Run: https://github.com/o/r/actions/runs/42" in body
    assert f"Build: {ENTRY['pack']['build']}" in body and "not the merge button" in body

def test_publish_opens_a_pr_and_never_pushes_main(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, maintainer=True)       # records every run() argv, answers gh queries
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    flat = [" ".join(c) for c in calls]
    assert any(c.startswith("gh release create demo-v1") and "--draft" in c for c in flat)
    assert any(c.startswith("git push -u origin publish/demo-v1") for c in flat)
    assert any("gh pr create" in c and "--label publish" in c and "--label automerge" in c for c in flat)
    assert not any(c.startswith("git push") and "main" in c.split()[-1] for c in flat)

def test_a_non_maintainer_publish_gets_no_automerge(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, maintainer=False)
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    assert not any("--label automerge" in " ".join(c) for c in calls)
```

`ENTRY`, `tiny_pack_with_stamp` (the Task 1 helper plus `meta["pipeline"]`) and `fake_gh_and_git` (monkeypatches `publish_pack.run` to record argv and return canned output for `gh release list`, `gh api user`, `git rev-parse`, `git branch -r --contains`) go at the top of the test file.

- [ ] **Step 3: Run them to see them fail.** `python -m pytest pipeline/tests/test_publish_pack.py -v`. Expected: the new tests FAIL (`AttributeError: ... stamp_problem`).
- [ ] **Step 4: Implement** the interfaces above in `publish_pack.py`; delete `ready_to_commit`; `on_origin_main` is `git branch -r --contains <sha>` listing `origin/main` after `git fetch origin main`. Write `.github/maintainers.txt` with a comment line and `drewkeriazes`. Update the module docstring's steps 3 and 4.
- [ ] **Step 5: Run all tests.** `python -m pytest pipeline/tests -q`. Expected: all pass.
- [ ] **Step 6: Dry run against a real pack.** `python pipeline/publish_pack.py packs/park-city-mountain --tier silver --dry-run` from the main checkout. Expected: the entry prints with `"pipeline": "039b9a7"` and the branch `publish/park-city-mountain-v2`; nothing on GitHub changes.
- [ ] **Step 7: Commit.** `git add pipeline/publish_pack.py pipeline/tests/test_publish_pack.py .github/maintainers.txt && git commit -m "FEAT-272: publish_pack.py uploads a draft release and opens a publish PR instead of pushing to main"`

---

### Task 3: `resort.py add`: ride on request, an open publish PR counts as done

**Files:**
- Modify: `pipeline/resort.py` (`ADD_STAGES` handling in `cmd_add`, `published`, the `add` argparser near `:1452`)
- Test: `pipeline/tests/test_resort_add.py`

**Interfaces:**
- Consumes: `publish_pack.publish_branch` (Task 2).
- Produces: `publish_pending(slug: str, build: str, runner=default_runner) -> str | None`: the URL of an open PR labelled `publish` whose head branch starts with `publish/<slug>-v` and whose body contains `Build: <build>`; `None` otherwise (`gh pr list --label publish --state open --json url,headRefName,body`). New flag `--ride` on `add`.
- `cmd_add` runs the `ride` stage only with `--ride` (`--from ride` alone no longer implies it). The publish stage skips with `publish: skip: <url> is open for this build` when `publish_pending` returns a URL.

- [ ] **Step 1: Write the failing tests** (update the `world` fixture so `publish_pending` is monkeypatched to `world.pending`, default `None`):

```python
def test_add_skips_the_ride_unless_asked(world):
    world.add()
    assert "ride" not in [c[0] for c in world.calls]
    world.calls.clear(); world.add(ride=True)
    assert "ride" in [c[0] for c in world.calls]

def test_an_open_publish_pr_for_this_build_skips_publish(world, capsys):
    world.pending = "https://github.com/o/r/pull/9"
    world.add()
    assert not any(c[0] == "publish" for c in world.calls)
    assert "publish: skip: https://github.com/o/r/pull/9 is open for this build" in capsys.readouterr().out
```

Update `test_add_runs_every_stage_in_order_and_prints_the_gate` and `test_no_publish_and_from` to the order without `ride`.

- [ ] **Step 2: Run to see them fail.** `python -m pytest pipeline/tests/test_resort_add.py -v`. Expected: the two new tests FAIL.
- [ ] **Step 3: Implement** in `resort.py`; `add_resort.cmd` needs no change.
- [ ] **Step 4: Run all tests.** `python -m pytest pipeline/tests -q`. Expected: all pass.
- [ ] **Step 5: Commit.** `git commit -am "FEAT-272: resort.py add rides only with --ride and treats an open publish PR for the build as published"`

---

### Task 4: `publish-check`: the draft zip against its catalog entry, linted

**Files:**
- Create: `pipeline/publish_check.py`
- Modify: `.github/workflows/checks.yml` (the `changes` filter; a new `publish-check` job; the header comment table)
- Test: `pipeline/tests/test_publish_check.py`

**Interfaces:**
- Consumes: `pack_lint.lint_zip` (Task 1), `publish_pack.all_entries` (existing).
- Produces:
  - `changed_entries(base: dict, head: dict) -> list[dict]`: entries in `head` (resorts and test) whose `(slug, pack.formatVersion)` is new or whose `pack` differs from `base`.
  - `zip_problems(entry: dict, zip_path: str) -> list[str]`: size vs `pack.bytes`, sha256 vs `pack.sha256`.
  - CLI: `python pipeline/publish_check.py --base <catalog.json> --head <catalog.json> --repo <owner/name>`: for each changed entry, `gh release download <slug>-v<version> -p <slug>.zip -D <tmp> -R <repo>` (drafts included with a write token), then `zip_problems` + `lint_zip`; prints problems per slug; exit 1 if any.

Job `publish-check` in `checks.yml`:
- `changes` gets a second filter `catalog: ['catalog.json']` and output `catalog`.
- `needs: changes`, `if: github.event_name == 'pull_request' && needs.changes.outputs.catalog == 'true'`, `permissions: contents: write` (draft assets need push access), `timeout-minutes: 20`.
- Steps: checkout `main` into `main/` (`actions/checkout` with `ref: main`, `path: main`); checkout the PR head into `pr/` with `sparse-checkout: catalog.json`; setup Python 3.13 and `pip install -r main/pipeline/requirements.txt`; run `python main/pipeline/publish_check.py --base main/catalog.json --head pr/catalog.json --repo ${{ github.repository }}` with `GH_TOKEN: ${{ github.token }}`.

- [ ] **Step 1: Write the failing tests:**

```python
def test_changed_entries_finds_a_new_version_only():
    base = {"resorts": [entry("vail", 3)], "test": [entry("synth", 2)]}
    head = {"resorts": [entry("vail", 4)], "test": [entry("synth", 2)]}
    assert [(e["slug"], e["pack"]["version"]) for e in changed_entries(base, head)] == [("vail", 4)]

def test_zip_problems_catches_size_and_hash(tmp_path):
    z = tmp_path / "demo.zip"; z.write_bytes(b"abc")
    e = entry("demo", 1, size=3, sha256=hashlib.sha256(b"abc").hexdigest())
    assert zip_problems(e, str(z)) == []
    assert any("sha256" in p for p in zip_problems({**e, "pack": {**e["pack"], "sha256": "0" * 64}}, str(z)))
    assert any("bytes" in p for p in zip_problems({**e, "pack": {**e["pack"], "bytes": 4}}, str(z)))
```

- [ ] **Step 2: Run to see them fail.** `python -m pytest pipeline/tests/test_publish_check.py -v`. Expected: FAIL, no module.
- [ ] **Step 3: Implement** `publish_check.py` and the `checks.yml` changes (add `publish-check` to the header table: "the changed catalog entry's draft zip: size, sha256, pack_lint.py; scripts from main | catalog.json changed").
- [ ] **Step 4: Run all tests.** `python -m pytest pipeline/tests -q`. Expected: all pass.
- [ ] **Step 5: Commit.** `git add pipeline/publish_check.py pipeline/tests/test_publish_check.py .github/workflows/checks.yml && git commit -m "FEAT-272: publish-check downloads a publish PR's draft zip and checks it against its catalog entry"`

---

### Task 5: Merge decisions and the catalog refresh

**Files:**
- Create: `pipeline/publish_merge.py`
- Test: `pipeline/tests/test_publish_merge.py`

**Interfaces:**
- Consumes: `publish_pack.update_catalog`, `publish_pack.maintainers`, `publish_pack.all_entries`, `publish_check.changed_entries` (Task 4).
- Produces (pure, no I/O):
  - `publish_file_patterns(slug: str) -> list[str]`: `catalog.json`, `RELEASES.md`, `reports/<slug>.md`, `resorts/<slug>/**`, `manifests/<slug>.json`.
  - `parse_branch(ref: str) -> tuple[str, int] | None`: `"publish/park-city-mountain-v2"` -> `("park-city-mountain", 2)`.
  - `files_ok(files: list[str], slug: str) -> bool`.
  - `label_ok(events: list[dict], label: str, maintainers: set[str], app_login: str, body: str, run_actor: Callable[[int], str | None]) -> bool`: the most recent `labeled` event for `label` (timeline API shape: `{"event": "labeled", "label": {"name": ...}, "actor": {"login": ...}, "created_at": ...}`) was by a maintainer, or by `app_login` on a PR whose body has `Run: https://github.com/<repo>/actions/runs/<id>` and `run_actor(id)` is a maintainer.
  - `commits_after_label_ok(commits: list[dict], label_time: str, app_login: str) -> bool`: no commit dated after `label_time` except ones authored by `app_login` (the refresh).
  - `rebase_catalog(base: dict, pr: dict, main: dict) -> dict`: applies `publish_check.changed_entries(base, pr)` onto `main` with `update_catalog`.
  - `decide(*, labels: list[str], files: list[str], branch: str, checks: list[dict], automerge_ok: bool, behind_main: bool) -> str`: one of `"merge"`, `"refresh"`, `"wait"`, `"refuse: <why>"`. `checks` items `{"name", "conclusion"}`; all must be `success` or `skipped`.
- CLI (thin `gh` wrapper, Task 6 calls it): `python pipeline/publish_merge.py ready <pr>`, `python pipeline/publish_merge.py closed <pr>`. `ready`: gathers PR data with `gh api`, calls `decide`, then: `refresh` regenerates `catalog.json` with `rebase_catalog` on the PR branch and pushes; `merge` runs `gh release edit <tag> --draft=false` **only if that release is a draft**, then `gh pr merge <pr> --squash`. A rollback PR (spec section 3) is a `publish/<slug>-v<N>` branch whose catalog points back at an already published `v<N>`: no draft, so it just merges. `closed`: merged with the release still a draft publishes it; unmerged deletes the draft (`gh release delete <tag> --yes`, only if it is a draft).

- [ ] **Step 1: Write the failing tests:**

```python
def test_parse_branch():
    assert parse_branch("publish/park-city-mountain-v2") == ("park-city-mountain", 2)
    assert parse_branch("issue-69-publish-pr") is None

def test_files_outside_the_publish_set_are_refused():
    ok = ["catalog.json", "reports/vail.md", "resorts/vail/vail.json", "manifests/vail.json"]
    assert files_ok(ok, "vail")
    assert not files_ok(ok + ["pipeline/build_pack.py"], "vail")
    assert not files_ok(["resorts/bigsky/bigsky.json"], "vail")

def test_label_from_a_maintainer_counts():
    assert label_ok([labeled("automerge", "drewkeriazes")], "automerge", {"drewkeriazes"}, "pub[bot]", "", lambda i: None)

def test_label_from_a_non_maintainer_is_refused():
    assert not label_ok([labeled("automerge", "someone")], "automerge", {"drewkeriazes"}, "pub[bot]", "", lambda i: None)

def test_label_from_the_app_counts_only_for_a_maintainer_run():
    body = "Run: https://github.com/o/r/actions/runs/42"
    ev = [labeled("automerge", "pub[bot]")]
    assert label_ok(ev, "automerge", {"drewkeriazes"}, "pub[bot]", body, lambda i: "drewkeriazes" if i == 42 else None)
    assert not label_ok(ev, "automerge", {"drewkeriazes"}, "pub[bot]", body, lambda i: "someone")

def test_a_commit_after_the_label_blocks_unless_it_is_the_refresh():
    t = "2026-11-12T10:00:00Z"
    assert not commits_after_label_ok([commit("2026-11-12T11:00:00Z", "someone")], t, "pub[bot]")
    assert commits_after_label_ok([commit("2026-11-12T11:00:00Z", "pub[bot]")], t, "pub[bot]")

def test_rebase_catalog_keeps_both_resorts():
    base = {"resorts": []}; pr = {"resorts": [entry("a", 1)]}; main = {"resorts": [entry("b", 1)]}
    assert sorted(r["slug"] for r in rebase_catalog(base, pr, main)["resorts"]) == ["a", "b"]

def test_decide():
    green = [{"name": "publish-check", "conclusion": "success"}, {"name": "pipeline-tests", "conclusion": "skipped"}]
    args = dict(labels=["publish", "automerge"], files=["catalog.json"], branch="publish/a-v1", checks=green,
                automerge_ok=True, behind_main=False)
    assert decide(**args) == "merge"
    assert decide(**{**args, "behind_main": True}) == "refresh"
    assert decide(**{**args, "labels": ["publish"]}) == "wait"
    assert decide(**{**args, "checks": [{"name": "publish-check", "conclusion": "failure"}]}) == "wait"
    assert decide(**{**args, "automerge_ok": False}).startswith("refuse")
    assert decide(**{**args, "files": ["catalog.json", "pipeline/x.py"]}).startswith("refuse")

def test_merged_pr_with_a_draft_publishes_it(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": True, "headRefName": "publish/a-v1"}, release_draft=True)
    publish_merge.main(["closed", "7"])
    assert ["gh", "release", "edit", "a-v1", "--draft=false"] in calls

def test_a_rollback_merges_without_touching_a_published_release(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=False, decision="merge")
    publish_merge.main(["ready", "7"])
    assert not any(c[:3] == ["gh", "release", "edit"] for c in calls)
    assert any(c[:3] == ["gh", "pr", "merge"] for c in calls)

def test_closed_unmerged_deletes_only_a_draft(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=True)
    publish_merge.main(["closed", "7"])
    assert any(c[:3] == ["gh", "release", "delete"] for c in calls)
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=False)
    publish_merge.main(["closed", "7"])
    assert not any(c[:3] == ["gh", "release", "delete"] for c in calls)
```

- [ ] **Step 2: Run to see them fail.** `python -m pytest pipeline/tests/test_publish_merge.py -v`. Expected: FAIL, no module.
- [ ] **Step 3: Implement** `publish_merge.py`. Ordering inside `ready` when `decide` says `merge`: re-check that the release is still a draft, publish it, then merge; if the merge call fails after publishing, retry it 3 times 20 s apart, then comment on the PR with the error and exit 1.
- [ ] **Step 4: Run all tests.** `python -m pytest pipeline/tests -q`. Expected: all pass.
- [ ] **Step 5: Commit.** `git add pipeline/publish_merge.py pipeline/tests/test_publish_merge.py && git commit -m "FEAT-272: publish_merge.py decides release-then-merge, refresh or refuse for a publish PR"`

---

### Task 6: The workflows, the GitHub App, and the reviewer skip

**Files:**
- Create: `.github/workflows/publish-merge.yml`
- Modify: `.github/workflows/pr-review.yml` (a first step that ends the job for a pure publish PR)
- Test: `pipeline/tests/test_workflows.py` (static checks on the YAML)

**Interfaces:**
- Consumes: `publish_merge.py` CLI (Task 5), `publish_merge.files_ok` (for the reviewer skip, via `python pipeline/publish_merge.py pure <pr>` which prints `true`/`false`; add this subcommand here).
- `publish-merge.yml`:
  - `on: workflow_run: {workflows: [Checks], types: [completed]}` and `pull_request_target: {types: [labeled, closed]}`. `concurrency: {group: publish-merge, cancel-in-progress: false}`.
  - Job runs only when the PR head branch starts with `publish/` (from `github.event.workflow_run.head_branch` or `github.event.pull_request.head.ref`).
  - Steps: `actions/create-github-app-token` with `app-id: ${{ secrets.PUBLISH_APP_ID }}`, `private-key: ${{ secrets.PUBLISH_APP_KEY }}`; checkout `main` (never the PR); setup Python; `python pipeline/publish_merge.py ready <pr>` (workflow_run or labeled) or `closed <pr>` (closed), with `GH_TOKEN` = the App token.
- `pr-review.yml`: before the review steps, `python pipeline/publish_merge.py pure ${{ github.event.pull_request.number }}` (checkout of `main`, `GH_TOKEN: github.token`); when it prints `true`, the remaining steps are skipped.

- [ ] **Step 1 (Drew, by hand): create the GitHub App.** Settings > Developer settings > GitHub Apps > New: name "MapPacker publisher", no webhook, repository permissions Contents: write, Pull requests: write, Issues: read (timeline), Actions: read, Metadata: read; install on `MapPacker-SnowboardAnywhere` only. Generate a private key. Add repo secrets `PUBLISH_APP_ID` and `PUBLISH_APP_KEY`. Expected: `gh secret list` shows both.
- [ ] **Step 2: Write the failing tests** in `test_workflows.py` (load YAML with `yaml.safe_load`; PyYAML is a test dependency already if present, else add to the test install line in `checks.yml`):

```python
def test_publish_merge_never_checks_out_the_pr():
    wf = load(".github/workflows/publish-merge.yml")
    for step in all_steps(wf):
        if step.get("uses", "").startswith("actions/checkout"):
            assert step.get("with", {}).get("ref") in (None, "main")

def test_publish_merge_uses_the_app_token_and_one_at_a_time():
    wf = load(".github/workflows/publish-merge.yml")
    assert wf["concurrency"]["group"] == "publish-merge"
    assert any("create-github-app-token" in s.get("uses", "") for s in all_steps(wf))

def test_review_runs_on_a_publish_pr_with_code():
    assert publish_merge.files_ok(["catalog.json", "pipeline/x.py"], "a") is False   # pure -> false -> review runs
    wf = load(".github/workflows/pr-review.yml")
    assert any("publish_merge.py pure" in s.get("run", "") for s in all_steps(wf))
```

- [ ] **Step 3: Run to see them fail.** `python -m pytest pipeline/tests/test_workflows.py -v`. Expected: FAIL (file missing).
- [ ] **Step 4: Implement** the two workflow changes and the `pure` subcommand.
- [ ] **Step 5: Run all tests.** `python -m pytest pipeline/tests -q`. Expected: all pass.
- [ ] **Step 6: Commit.** `git add .github/workflows/publish-merge.yml .github/workflows/pr-review.yml pipeline/publish_merge.py pipeline/tests/test_workflows.py && git commit -m "FEAT-272: publish-merge.yml releases then merges trusted publish PRs with the App token; the reviewer skips pure publish PRs"`

---

### Task 7: Switch over: required checks, docs, and an end-to-end publish

**Files:**
- Modify: `CLAUDE.md` (the "publishing aside" exception, "commits ... straight to `main`", the `--synth` "on main" step), `README.md` (Build a resort steps 5 and 6, Publishing, the synthetic pack, Checks table), `.claude/skills/pack-build/SKILL.md`, `.claude/agents/pr-reviewer.md` (publish PRs: what to look at when one is reviewed), `docs/pack-format.md` (Contract rows citing `publish_pack.py` line numbers)

- [ ] **Step 1: Docs.** Replace every description of the direct publish commit with the PR flow: draft release, `publish/<slug>-v<N>` PR, `publish-check`, `publish-merge.yml` releases then merges, the `automerge` label as approval, never the merge button, `--ride` for a local ride. Check: `git grep -n "straight to .main\|publishing aside\|main checkout on .main" -- CLAUDE.md README.md .claude docs/pack-format.md` prints nothing.
- [ ] **Step 2: Run all tests and push.** `python -m pytest pipeline/tests -q` (all pass), `SA_SKIP_GPU_BUDGETS=1 git push`. Open the build PR (`Fixes #69`) and wait for Checks and the Claude review; address findings.
- [ ] **Step 3 (after Drew merges the build PR): require the checks.** Add a `required_status_checks` rule to ruleset 27094401 with contexts `changes`, `pipeline-tests`, `format-check`, `synth-pack`, `render-budgets`, `repo-rules`, `public-guards`, `publish-check` (strict: false), keeping the existing three rules and no bypass actors: `gh api -X PUT repos/drewkeriazes/MapPacker-SnowboardAnywhere/rulesets/27094401 --input <file>`. Expected: `gh api .../rulesets/27094401 --jq '[.rules[].type], .bypass_actors'` shows four rules and `[]`.
- [ ] **Step 4: End to end with the synthetic pack.** On `main`: `python pipeline/publish_pack.py --synth --force`. Expected, in order: a draft release `synth-v3`; a PR `publish/synth-v3` labelled `publish` and `automerge`; Checks green with `publish-check` passing; `publish-merge.yml` publishes `synth-v3` and merges the PR; `catalog.json` on `main` lists synth v3; no Claude review on that PR. Then `cd ../SnowboardAnywhere/game && npm run get synth -- --force` installs v3.
- [ ] **Step 5: The refusal paths, for real.** Open a throwaway publish PR by hand that also changes `pipeline/README.md` (any file outside the set) with `publish` and `automerge`. Expected: `publish-merge.yml` comments "refuse: files outside the publish set" and does not merge; the Claude reviewer reviews it. Close it; expected: its draft (if any) is deleted.
- [ ] **Step 6: Commit any doc fixes from steps 4 and 5** and report the run links on the card.
