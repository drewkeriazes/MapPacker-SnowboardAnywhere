# Publishing a pack through a pull request

Date: 2026-11-12. Status: design, for Drew's approval. Cards: FEAT-272 (#69, below "the publish card"), and amendments to FEAT-245 (#21), FEAT-264 (#24), FEAT-265 (#25), FEAT-271 (#68) and EPIC-17 (SnowboardAnywhere#565).

## Why

Publishing a pack today ends with `publish_pack.py` committing `catalog.json`, the report and the resort's files and pushing them straight to `main` (`pipeline/publish_pack.py:293-308`). On 2026-11-12 the "protect main" ruleset started requiring a pull request for every change to `main`; to keep publishing working, an admin bypass was added, and Vail v3 and Park City v1 went out through it. Drew has since removed the bypass by hand (the ruleset now has no bypass actors), so **publishing is currently broken at the push step**: the release is created, then the catalog push is refused.

Drew's intent, in his words: the admin bypass "should not be something we do regularly"; "I'd like changes to go through a PR process"; when adding Park City he expected "a PR created to add the info / build the pack / then set the release." Adding a resort is a change to the repo like any other and should be visible and gated the same way.

The same publish step is also what FEAT-245's build-pack workflow (a resort built in GitHub Actions) and EPIC-17's in-game "Build it" button end in, so it has to work from Drew's PC and from a workflow, and has to hold up if, long term, people other than Drew trigger builds. Drew: "that doesn't mean design choices should be lazy for the app."

## Goals

1. Nothing pushes to `main`. Every publish (a resort, a republish, the synthetic test pack) arrives as a pull request.
2. One publish path, started from either Drew's PC (`add_resort.cmd`, `publish_pack.py`) or the FEAT-245 workflow.
3. The release goes live together with its catalog entry: published by the merge workflow seconds before it merges the PR (section 3), never without the merge following and never after a catalog that names it.
4. A publish PR that Drew (or a listed maintainer) started merges by itself once its checks pass. A publish started by anyone else waits for a person to merge it.
5. The checks on a publish PR check the file players will download (the uploaded zip), not the publisher's word for it.
6. CI runs only checks that earn their time. A pack is data plus a contract; how the game draws and simulates a pack is tested in the game repo.

## Non-goals

- Moving the build itself into CI. That is FEAT-245; this design only gives it a publish step to call.
- Changing the pack format, `catalog.json`'s schema as the game reads it, or how the game downloads a pack (`get_pack.mjs` reads `entry.pack.url` from the catalog and keeps doing so).
- Fixing the game's 5 minute stale catalog (SnowboardAnywhere BUG-096, #579). It still applies after a merge; it is not made worse.
- A headless ride or any GPU render of a real pack in CI (see "Checks").

## Anti-goals (would make this a failure even if it works)

- Any standing bypass of the `main` rule: neither the admin "always" bypass nor GitHub's "bypass only through a pull request" mode. Drew rejected both. An emergency direct push means Drew switches the ruleset off by hand and back on afterwards: deliberate and in GitHub's audit log.
- A catalog entry on `main` that points at a download that is not live (a 404 for every player).
- Slow or flaky checks that do not catch pack problems (a CI ride that takes minutes to tell us the board stands on a hill).
- Auto-merging content that nobody trusted started.

## Constraints and facts

- The repo is public. GitHub Actions minutes on standard runners are free for public repos.
- Ruleset "protect main" (id 27094401): rules `deletion`, `non_fast_forward`, `pull_request` with `required_approving_review_count: 0`; no bypass actors; **no required status checks** today. Repo setting `allow_auto_merge: true`, `delete_branch_on_merge: true`.
- A PR opened (or a branch pushed) with a workflow's built-in `GITHUB_TOKEN` does not start other workflows, so its Checks never run. `pr-feedback.yml` already works around this by dispatching Checks by hand.
- `checks.yml` jobs skip themselves with `if:` when `pipeline/` did not change (`dorny/paths-filter`, the `changes` job); a skipped job counts as passed for a required check. There is no workflow-level `paths:` filter (which would leave a required check pending forever) and there must not be one.
- `pr-review.yml` (the Claude reviewer) runs on every PR.
- Release assets: 2 GiB limit per asset (`MAX_ZIP` 1.9 GiB in `publish_pack.py`). Draft releases and their assets are visible only to users with push access, through the API; their public download URL works only once the release is published.
- `publish_pack.py` today requires the main checkout on `main`, records `git rev-parse --short HEAD` as the catalog's `pipeline`, and only warns when `pipeline/` has uncommitted changes.
- `catalog.json` is read by the game from `raw.githubusercontent.com/.../main/catalog.json`; its `pack.url` is the only way the game finds a zip. Tag names are a MapPacker-only concern.
- Builds need the data hosts (USGS, Planetary Computer, S3 lidar, Mapterhorn, Overpass, LFPS), several GB of raw data, and today a GPU for the ride and the menu shots. Only the first two matter for this design (the ride leaves the gate, below).

## The design

### 1. `publish_pack.py` opens a publish PR

Same command and flags as today (`publish_pack.py packs/<slug>`, `--synth`, `--test`, `--status`, `--tier`, `--dry-run`), plus `--accept-change` (FEAT-264, below). It no longer needs the main checkout or `main`; it runs from any checkout or worktree. Steps:

1. **Refuse an unreproducible build.** The commit checked is the one that built the pack: `meta.json`'s `pipeline` stamp (`packwriter.pipeline_commit`), not the publisher's checkout. It must be present, carry no `+dirty`, and exist on `origin/main`. The catalog's `pipeline` becomes that build stamp (today it is the publisher's `HEAD`). A pack built from a branch, or from uncommitted pipeline code, is not published; a pack with no stamp (today `packs/bigsky`, `packs/breckenridge`) is rebuilt before it can be republished.
2. **Version and tag.** Next version for the slug from the repo's release list, drafts included (`gh release list` names a draft's intended tag even though GitHub creates the git tag only when the release is published), so two publishes in flight never pick the same number. Tag `<slug>/v<N>` per FEAT-271.
3. **Zip and upload a draft release** with the zip, `meta.json` and the report, title `<Name> v<N>`, notes that include the FEAT-264 diff. The draft is invisible to players and to the catalog.
4. **Build the PR branch in a throwaway worktree** off a fresh `origin/main` (never the publisher's checkout): `catalog.json` with the new entry, `RELEASES.md` regenerated (FEAT-271), `reports/<slug>.md`, and the resort's own files (`resorts/<slug>/`, `manifests/<slug>.json`), exactly the files today's publish commit carries. Branch `publish/<slug>-v<N>`. Commit message as today: `<slug> v<N>: <status>, <MB> MB, pipeline <sha>`.
5. **Open the PR** with label `publish` (and `automerge` when the publisher is trusted, section 4), body: the report's gate summary, the FEAT-264 before/after table, the draft release link, size and sha256, who started it and from where (local or run link). GitHub's native auto-merge is not turned on; `publish-merge.yml` does the merge (section 3).
6. Print the PR link. The command does not wait for the merge.

`resort.py add`'s publish stage calls this unchanged; its "published" skip (catalog already has this build) also counts an open publish PR for the same build as done, so a rerun does not open a second PR.

### 2. Checks on a publish PR

Required status checks are added to the ruleset (the publish card): the existing `checks.yml` jobs plus the new `publish-check` job. This also makes "a failed check blocks" real for every PR, which today is only a convention (CLAUDE.md).

New job `publish-check` in `checks.yml`, runs when `catalog.json` changed, skips (passes) otherwise:

- **FEAT-265 catalog check** (`pipeline/check_catalog.py`): schema, the slug matches `resorts/<slug>/`, and for the new or changed entry: its release exists (draft allowed on a PR), the zip asset's size and sha256 equal the entry's `bytes` and `sha256`. The job downloads the draft's zip through the API to hash it.
- **Pack lint** (new, `pipeline/pack_lint.py`, seconds): on the downloaded zip, every file `meta.json` names exists and decodes (height and mask tiles as images of the stated size, instance files a whole number of records, JSON parses), `meta.json`, `features.json` and the stand and attract files match `docs/pack-format.md`, `formatVersion` equals the pipeline's `FORMAT_VERSION`, `report.json` belongs to this build (`build` matches `meta.json`). Also **size ceilings**, so a real pack too heavy for the game is caught without rendering it: zip bytes, crowns plus stems per km², fine tile count. Starting ceilings are the builder's call from the published packs (Vail, Breckenridge, Big Sky, Boston Mills, Ohio Hills, Park City) with headroom; they are named constants beside the DATA-022 thresholds in `pack_report.py`.
- **FEAT-264 big-change check** (the card says "regression"; it means a rebuilt pack whose numbers moved a lot from the previous version, which is either a broken stage or an intended change): the new report's numbers against the previous version's (`reports/<slug>.md` / report asset at the last catalog entry). A metric moving more than the threshold (15% to start) fails the check, for trusted publishes too. The override is explicit and happens **on the open PR**, with no rebuild and no new version: a maintainer adds the label `accept-change` (who added it is verified as for `automerge`, section 4), and the check reruns and passes, listing the accepted changes. `publish_pack.py --accept-change` just adds that label when it opens the PR, for a publisher who already knows. This works the same for a pack built in CI, whose zip exists only in the draft. First version of a slug: nothing to compare, passes.
- The DATA-022 gate itself stays where it is: `publish_pack.py` refuses `--status playable` unless the report passes, and the status is in the catalog entry the check validates.

`format-check` already compares the pack format with the game's `main`; it runs when `pipeline/` changed, which a publish PR does not touch, so the pack lint's `formatVersion` line is the publish-time version of it.

`pr-review.yml` skips a PR only when it is labelled `publish` **and** changes nothing outside the publish file set (section 3). A `publish` PR that touches anything else gets the normal review, so the label can't switch review off. (My call: for a pure publish the checks are the gate; a model review of a catalog entry costs tokens and adds nothing.)

### 3. Merge, then the release goes live

New workflow `publish-merge.yml`, `concurrency: publish-merge` (one at a time). It runs when a `publish` PR's checks finish green (on `check_suite` / `workflow_run` completion, builder's call) and, for PRs labelled `automerge`, does, in this order:

1. **Bring the branch up to date if `main` moved.** Two publishes in flight both change `catalog.json` and `RELEASES.md`, so the second one conflicts. The workflow regenerates both from the current `main` plus this PR's entry (a small script, not a text merge), pushes to the PR branch with the App token (section 4) so Checks run again, and stops; the green run that follows comes back here.
2. **Publish the draft release** (`gh release edit <tag> --draft=false`).
3. **Merge the PR** (squash; the branch is deleted on merge), with the App token rather than `GITHUB_TOKEN`, so the workflows that run on a push to `main` (Checks, FEAT-265's catalog check) still start.

Before step 1, the workflow checks that the PR may merge itself at all:
- the `automerge` label was added by a maintainer (read from the PR's timeline), or by the App on a publish whose run a maintainer started (the run id is in the PR body; the workflow looks up its `triggering_actor`);
- no commit was pushed to the PR after the label, other than the workflow's own conflict refresh;
- the PR changes only the publish file set: `catalog.json`, `RELEASES.md`, `reports/<slug>.md`, `resorts/<slug>/`, `manifests/<slug>.json`. A `publish` PR that touches anything else (code, workflows) is not a publish and never merges itself.

`publish-check` and `publish-merge.yml` run `check_catalog.py` and `pack_lint.py` from `main`, not from the PR branch, because they hold a token that can read draft releases and a PR must not be able to change the code that checks it.

Releasing before merging means the catalog never names a download that is not live. If step 3 fails after step 2, the release is public but nothing points at it (players are unaffected); the workflow retries the merge and reports on the PR.

The workflow does the merge, not GitHub's native auto-merge, because native auto-merge would merge without publishing the draft first. The `automerge` label marks a trusted publish.

A PR without `automerge` (an untrusted publish) waits. A maintainer approves it by adding the `automerge` label, and the workflow then does the same release-then-merge. Nobody merges a publish PR with the merge button: merging before the release is published would put a dead URL in the catalog. GitHub can't stop a button merge from inside the PR, so this is a rule in CLAUDE.md and in the PR body ("approve with the `automerge` label, not the merge button"). As a safety net, `publish-merge.yml` also runs on any merged `publish` PR and publishes a draft it finds still unpublished, so a button merge leaves a dead URL for seconds, not until someone notices.

**A closed, unmerged publish PR** deletes its draft release (`publish-merge.yml` on `pull_request: closed` without merge).

**Rolling back** a bad pack: a PR that reverts its catalog entry (points the slug back at the previous version), labelled `publish` + `automerge`; it has no draft to release, so the workflow just merges it after checks. The bad release stays on GitHub with nothing pointing at it; deleting it is a separate, manual choice.

### 4. Trust: who may auto-merge

Trust is decided by **who started the build**, not by what button was pressed.

- A **local publish** is trusted when `gh`'s signed-in user is in the maintainers list (`.github/maintainers.txt`, today one line: Drew's GitHub login). `.github/maintainers.txt` is the trust list for **GitHub identities** only (local publishes, a workflow's `triggering_actor`); it is separate from the game account role above.
- A **workflow publish** (FEAT-245) is trusted when `github.triggering_actor` is in the maintainers list. `workflow_dispatch` already needs write access; the list is the explicit rule on top of that.
- The **in-game "Build it" button** (EPIC-17) is gated on the **game account**, not on a GitHub identity (Drew's decision). The game has accounts (FEAT-273, SnowboardAnywhere#600, Firebase Authentication): Play as guest, Sign in with GitHub, and later email and password (FEAT-274, #603), all linked to one account per player; Drew's account is player 1. `maintainer` is a **role on that account** (a Firebase custom claim set only server-side). A guest never sees Build it. The dev server verifies the session token and refuses `/api/resorts/build` unless the account has the `maintainer` role, then runs the workflow and passes the account id as `requested_by`, which FEAT-245 writes into the publish PR. Because the server runs the workflow with Drew's `gh`, `triggering_actor` is Drew for every such run: the account role is the check that decides who may ask, and `requested_by` makes the requester visible on the PR.
- Anything started **automatically from an issue** (a future FEAT-266 resort request handed to the workflow) or by anyone not in the list: the PR opens without `automerge` and waits for a maintainer to add the label.

Why the line matters even though only Drew triggers builds today: OSM names end up in the game (OSM can be vandalised); every build spends runner time and sends the LANDFIRE email to LFPS; and a resort name typed by a stranger is untrusted text inside a workflow, so workflows pass it as an environment variable and never interpolate it into a shell line.

**Workflow identity**: a GitHub App ("MapPacker publisher") installed on this repo with contents, pull requests and releases write. Its token opens FEAT-245's publish PRs and pushes the conflict refresh in section 3, so Checks run on them (the built-in token would not start them). Its app id and private key are repo secrets. A local publish uses Drew's `gh` login as today. Drew creates and installs the App by hand (a step in the publish card).

### 5. The ride leaves the gate

The headless ride (`resort.py ride`, `game/tools/shoot.mjs`) is no longer a stage of `resort.py add` by default; `--ride` keeps it for debugging a pack locally. It is not run in CI.

Reasoning (Drew's, agreed): a pack is assets plus a contract. What the ride caught in practice is a pack that fails to load, and each cause has a cheaper check: a format mismatch (`format-check`, the pack lint's `formatVersion`), missing or corrupt files (pack lint), bad values such as holes in the heights or a start in the trees (the DATA-022 report). How the game draws and moves on a pack is the game's logic, tested in the game repo's CI against the synthetic pack. The one thing the ride saw that nothing else did, a real pack being much heavier than the synthetic one, is covered by the size ceilings.

The menu shots and ghost runs (`attract`) and the compare spots (`spots`) also need the game to render. They stay polish lines in the report, not gated; on a runner without the game they skip as they do today.

### 6. The synthetic pack

`publish_pack.py --synth` uses the same path: draft release `synth/v<N>`, publish PR (catalog `test` list, no resort files), `publish` + `automerge` labels (a maintainer runs it), release-then-merge. It still publishes only when the content changed (FEAT-241). The "after merging a pipeline change, run `--synth` on main" step in CLAUDE.md stays, minus "on main".

## How the cards change

Order: the publish card, then FEAT-265 and FEAT-264 (its checks), then FEAT-271 (tags and `RELEASES.md` on top), then FEAT-245 (calls it from a workflow).

- **FEAT-272 (#69), the publish card.** Sections 1 (except the FEAT-271 tag scheme, which can land first with the old `<slug>-v<N>` tags), 3, 4, 5 and 6; the `publish-check` job skeleton with the pack lint and size ceilings; required status checks in the ruleset; `pr-review.yml` skips `publish`; the GitHub App (created by Drew). Docs: CLAUDE.md (the "publishing aside" exception and "commits ... straight to `main`" go), README (Build a resort, Publishing, the synthetic pack, Checks), `.claude/skills/pack-build/SKILL.md`, `.claude/agents/pr-reviewer.md`, `docs/pack-format.md` Contract row for `catalog.json` (line numbers move). Until this lands, publishing does not work (the bypass is gone); Drew can publish by hand by switching the ruleset off for the push, if a pack must go out sooner.
- **FEAT-265 (#25)**: no longer "the one file that skips review". `check_catalog.py` runs in `publish-check` on PRs (draft releases allowed) and weekly on `main` (published releases required, orphans listed, one `bug` issue on failure). `--deep` sha check is what `publish-check` does for the changed entry.
- **FEAT-264 (#24)**: the diff runs as a check on the publish PR and goes into the PR body and the release notes; an intended change is accepted with the `accept-change` label on the open PR (maintainer-added), not by republishing. Retitle from "blocks regressions" to "stops big changes from the previous version until accepted".
- **FEAT-271 (#68)**: tags `<slug>/v<N>`; `RELEASES.md` regenerated inside the publish PR (and in the conflict refresh); drop "`npm run get` resolves the newest `<resort>/v*` tag" (the game reads URLs from the catalog). Migration (Drew's decision): rename all 10 existing releases to the new tags in one migration PR that rewrites their catalog URLs in the same change. Drew is the only player today, so the few minutes of stale cached catalog (BUG-096) don't matter.
- **FEAT-245 (#21)**: runs on `ubuntu-latest`; first step a probe job that fetches one small item from each data host and fails loudly per host; LANDFIRE email from a repo secret; ends in `publish_pack.py` with the App token (step 3 "update `catalog.json` (same path as today)" goes); no ride; the attract and spots stages skip (no game on the runner); a resort too big for the runner (disk about 14 GB free, 16 GB RAM) is built on Drew's PC and published locally through the same PR path.
- **EPIC-17 (SnowboardAnywhere#565)**: the flow line says "self-hosted runner"; change it to the GitHub-hosted runner, and the release step to "publish PR, release, merge". Add a rule: Build it only for a signed-in maintainer (user 1), never for a guest.
- **Game cards under EPIC-17** (created): FEAT-273 (SnowboardAnywhere#600) accounts, guest play, Sign in with GitHub and the maintainer role, all on Firebase; FEAT-274 (#603) email and password, linked deliberately (never by matching email); BUG-110 (#604) the dev server stops listening on the whole network before the build endpoint lands. FEAT-246 (#566): Build it only for an account with the `maintainer` role, sends `requested_by`.
- **FEAT-245 (#21)** also gets the `requested_by` input.

## Left to the builder

- Exact required-check names in the ruleset, and how `publish-merge.yml` waits for checks.
- `check_catalog.py` and `pack_lint.py` internals, and the starting size ceilings.
- The conflict-refresh script.
- Whether the first publish card lands before or after the tag rename (either works; the design above assumes before).

## Calls I made (for Drew to check)

1. Draft release first, published by the merge workflow just before it merges.
2. The merge is done by `publish-merge.yml`, not GitHub's native auto-merge, and the `automerge` label is the trust marker; an untrusted publish is approved by a maintainer adding the label.
3. Pack lint plus size ceilings replace the ride as the load check; `--ride` stays for local debugging.
4. `publish_pack.py` refuses (not warns) a pack whose build stamp is missing, `+dirty`, or not on `origin/main`; the catalog's `pipeline` becomes the build stamp.
5. The Claude reviewer skips a `publish` PR only when it changes nothing outside the publish file set.
6. Maintainers list in `.github/maintainers.txt`.
7. A GitHub App, not a personal token, as the workflow's identity.
8. The `automerge` and `accept-change` labels count only when a maintainer added them (or the App, for a run a maintainer started); a `publish` PR that changes anything outside the publish file set never merges itself; the check scripts run from `main`.
9. Accepting a FEAT-264 big change is a label on the open PR, not a republish.
