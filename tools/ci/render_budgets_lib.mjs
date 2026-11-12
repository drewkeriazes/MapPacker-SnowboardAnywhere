// FEAT-240 (ported from SnowboardAnywhere's FEAT-176 / FEAT-183): the local render-budgets run (CI's
// `render-budgets` job in checks.yml, on Drew's GPU), shared by tools/ci/local_render_budgets.mjs (run by hand) and
// tools/ci/pre_push_render_budgets.mjs (the pre-push hook).
//
//   const ctx = prepare({ repo, sha, pr, mode })   preconditions; throws Stop with a reason on a refusal
//   const res = runCheck(ctx)                       builds, cishot.mjs on both packs, render_report.py
//   post(res)                                       the `render-budgets/local` status and the PR comment
//
// As in CI: one build of the game's main (the commit GitHub has as its main now, unpacked from the game clone with
// git archive into the cache and built once per game commit) draws the synthetic pack built by the merge base with
// origin/<base> ("before") and by the commit ("after"), with the game's game/tools/cishot.mjs, then the game's
// tools/ci/render_report.py and this repo's tools/ci/render_note.py. CI accepts the status only when it was set by
// the repo owner, on the exact head SHA, with the PR's current merge base, the same tools hash
// (tools/ci/render_budgets_key.sh), the same synthetic pack key and the same game commit, and the PR did not ask
// for stills.
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

export const MARKER = '<!-- ci-stills -->';
export const CONTEXT = 'render-budgets/local';
export const GAME_NAME = 'SnowboardAnywhere';
/** set on the `git push` that local_render_budgets.mjs --push makes, so the pre-push hook doesn't run the check again */
export const PUSH_GUARD = 'SA_RENDER_BUDGETS_PUSH';
/** testing aid for a machine without a GPU: the cishot flag, default --gpu. Never set on Drew's PC: the local run is
 *  meant to be the real GPU. */
const SHOT_FLAG = process.env.RB_SHOT_FLAG ?? '--gpu';
/** game builds kept in the cache (each is the game's tree plus a build, about 200 MB) */
const KEEP_GAME_BUILDS = 2;

export class Stop extends Error {}
const die = (msg) => { throw new Stop(msg); };
export const PYTHON = process.env.PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3');

// a hook runs with git's own variables set; the game clone and the archives are other checkouts, so drop them
const ENV = { ...process.env };
for (const k of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_PREFIX', 'GIT_OBJECT_DIRECTORY', 'GIT_COMMON_DIR']) delete ENV[k];

export function out(cmd, args, opts = {}) {
  return execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64 << 20, env: ENV, ...opts }).trim();
}
export function tryOut(cmd, args, opts = {}) { try { return out(cmd, args, opts); } catch { return null; } }

/**
 * Where child output and progress lines go. `log: 'inherit'` (by hand) prints everything; a file path (the hook)
 * writes the build and browser output there and prints only the step lines.
 */
function makeLog(log) {
  const t0 = Date.now();
  const fd = log === 'inherit' ? null : fs.openSync(log, 'a');
  const secs = () => Math.round((Date.now() - t0) / 1000);
  const write = (s) => { if (fd !== null) fs.writeSync(fd, `${s}\n`); };
  return {
    t0, secs, fd,
    step(title) { const s = `== ${title} (${secs()} s)`; write(s); console.log(fd === null ? `\n${s}` : `  ${s}`); },
    info(s) { write(s); if (fd === null) console.log(s); },
    warn(s) { write(s); console.warn(s); },
    run(cmd, args, opts = {}) {
      const r = spawnSync(cmd, args, { stdio: fd === null ? 'inherit' : ['ignore', fd, fd], env: ENV, ...opts });
      if (r.error) throw r.error;
      return r.status;
    },
    close() { if (fd !== null) fs.closeSync(fd); },
  };
}

// Git Bash, not WSL's bash.exe, on Windows (the .sh helpers need sha256sum, find and a POSIX sort)
function findBash() {
  if (process.env.RB_BASH) return process.env.RB_BASH;
  if (process.platform !== 'win32') return 'bash';
  const exec = out('git', ['--exec-path']); // .../Git/mingw64/libexec/git-core
  for (const c of ['../../../bin/bash.exe', '../../../usr/bin/bash.exe']) {
    const p = path.resolve(exec, c);
    if (fs.existsSync(p)) return p;
  }
  die('could not find Git Bash next to git; set RB_BASH to bash.exe');
}

export function defaultCache() {
  return path.resolve(process.env.RB_CACHE ?? path.join(os.homedir(), '.cache', 'mappacker-ci'));
}

/** the game clone: SBA_GAME_REPO, else SnowboardAnywhere next to this repo's main checkout (pipeline/paths.py) */
function gameClone(repo) {
  if (process.env.SBA_GAME_REPO) return path.resolve(process.env.SBA_GAME_REPO);
  const common = path.resolve(repo, out('git', ['rev-parse', '--git-common-dir'], { cwd: repo }));
  return path.join(path.dirname(path.dirname(common)), GAME_NAME);
}

/**
 * The PR for a number, a branch name, or (no argument) the current branch, or null (no PR, or gh not signed in).
 * REST, not `gh pr view`: GraphQL isn't reachable from cloud sessions.
 */
export function findPr(repo, which) {
  const full = tryOut('gh', ['repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner'], { cwd: repo })
    ?? tryOut('gh', ['api', 'repos/{owner}/{repo}', '--jq', '.full_name'], { cwd: repo });
  if (!full) return null;
  const shape = '{number, headRefOid: .head.sha, headRefName: .head.ref, baseRefName: .base.ref, labels: [.labels[] | {name}], '
    + 'state: (if .merged_at then "MERGED" else (.state | ascii_upcase) end), url: .html_url, '
    + `isCrossRepository: (.head.repo.full_name != "${full}")}`;
  let json;
  if (which && /^\d+$/.test(String(which))) {
    json = tryOut('gh', ['api', `repos/${full}/pulls/${which}`, '--jq', shape], { cwd: repo });
  } else {
    const branch = which ?? tryOut('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: repo });
    const owner = full.split('/')[0];
    json = tryOut('gh', ['api', `repos/${full}/pulls?state=open&head=${owner}:${encodeURIComponent(branch)}`, '--jq', `first(.[] | ${shape}) // empty`], { cwd: repo });
  }
  return json ? JSON.parse(json) : null;
}

/** the paths CI's `changes` filter turns render-budgets on for (checks.yml: the pipeline filter) */
export const BUDGET_PATHS = /^(pipeline\/|tools\/ci\/|\.github\/workflows\/checks\.yml$)/;

/**
 * Preconditions. mode 'manual': the commit is HEAD; it must be the PR's head on GitHub, or (push: true) ahead of it.
 * mode 'hook': the commit is about to be pushed to the PR's branch, so GitHub doesn't have it yet.
 */
export function prepare({ repo, sha = 'HEAD', pr: prArg, mode = 'manual', push = false, cache = defaultCache(), log = 'inherit' }) {
  const L = makeLog(log);
  const git = (...a) => out('git', a, { cwd: repo });
  const dirty = git('status', '--porcelain');
  if (dirty) die(`the working tree is not clean; commit first:\n${dirty}`);
  const HEAD = git('rev-parse', 'HEAD');
  const SHA = git('rev-parse', `${sha}^{commit}`);
  if (SHA !== HEAD) die(`the commit ${SHA.slice(0, 12)} is not this worktree's HEAD (${HEAD.slice(0, 12)})`);

  const pr = typeof prArg === 'object' && prArg ? prArg : findPr(repo, prArg);
  if (!pr) die('no PR found for this branch (or gh is not signed in). Open the PR first: its first push runs render-budgets in CI as usual.');
  if (pr.state !== 'OPEN') die(`PR #${pr.number} is ${pr.state.toLowerCase()}`);
  if (pr.isCrossRepository) die(`PR #${pr.number} comes from a fork; run it from a branch in this repo`);
  if (pr.labels.some((l) => l.name === 'stills')) die(`PR #${pr.number} has the stills label, so CI runs render-budgets anyway (the local run does not compare stills)`);

  const owner = out('gh', ['repo', 'view', '--json', 'owner', '--jq', '.owner.login'], { cwd: repo });
  const me = out('gh', ['api', 'user', '--jq', '.login'], { cwd: repo });
  if (me !== owner) die(`signed in to gh as ${me}; CI only trusts ${CONTEXT} statuses from ${owner}`);

  let needPush = false;
  if (mode === 'manual' && SHA !== pr.headRefOid) {
    if (!push) die(`HEAD ${SHA.slice(0, 12)} is not the head of PR #${pr.number} on GitHub (${pr.headRefOid.slice(0, 12)}). Push first, or run with --push.`);
    git('fetch', '-q', 'origin', pr.headRefName);
    if (tryOut('git', ['merge-base', '--is-ancestor', pr.headRefOid, 'HEAD'], { cwd: repo }) === null) {
      die(`HEAD does not fast-forward PR #${pr.number}'s branch ${pr.headRefName} (${pr.headRefOid.slice(0, 12)}); pull or rebase first`);
    }
    needPush = true;
  } else if (mode === 'manual') {
    const runs = tryOut('gh', ['api', `repos/{owner}/{repo}/actions/workflows/checks.yml/runs?head_sha=${SHA}`, '--jq', '.total_count'], { cwd: repo });
    if (runs && runs !== '0') L.info(`note: CI already started on ${SHA.slice(0, 12)}, so this pass applies to re-runs of it. Next time commit, then run with --push.`);
  }

  // the game's main as GitHub has it now: the commit CI's job asks for (checks.yml: "The game's main")
  const game = gameClone(repo);
  if (!fs.existsSync(path.join(game, 'game', 'package.json'))) die(`no ${GAME_NAME} checkout at ${game} (SBA_GAME_REPO)`);
  const GAME_SHA = out('gh', ['api', `repos/${owner}/${GAME_NAME}/commits/main`, '--jq', '.sha'], { cwd: repo });
  if (tryOut('git', ['cat-file', '-e', `${GAME_SHA}^{commit}`], { cwd: game }) === null) {
    L.info(`fetching the game's main (${GAME_SHA.slice(0, 12)}) into ${game}`);
    out('git', ['fetch', '-q', 'origin', 'main'], { cwd: game });
    if (tryOut('git', ['cat-file', '-e', `${GAME_SHA}^{commit}`], { cwd: game }) === null) die(`the game's main ${GAME_SHA.slice(0, 12)} is not in ${game} after a fetch`);
  }

  git('fetch', '-q', 'origin', pr.baseRefName);
  const BASE = git('merge-base', 'FETCH_HEAD', SHA);
  const BASH = findBash();
  const TOOLS = out(BASH, ['tools/ci/render_budgets_key.sh', SHA], { cwd: repo });
  L.info(`PR #${pr.number}: before = merge base ${BASE.slice(0, 12)} with origin/${pr.baseRefName}, after = ${SHA.slice(0, 12)}; `
    + `game ${GAME_SHA.slice(0, 12)}; tools ${TOOLS}; cache ${cache}`);
  return { repo, git, L, pr, owner, SHA, BASE, TOOLS, BASH, needPush, cache, game, GAME_SHA };
}

/** game/node_modules in the game clone matches the lockfile `lock` (a Buffer) as `npm ci` would install it */
function installedMatches(gameDir, lock) {
  const hiddenPath = path.join(gameDir, 'node_modules', '.package-lock.json');
  if (!fs.existsSync(hiddenPath)) return false;
  const want = JSON.parse(lock.toString('utf8')).packages ?? {};
  const have = JSON.parse(fs.readFileSync(hiddenPath, 'utf8')).packages ?? {};
  for (const [k, v] of Object.entries(want)) {
    if (!k.startsWith('node_modules/')) continue;
    if (!have[k]) { if (!v.optional) return false; continue; }
    if (v.version && have[k].version !== v.version) return false;
  }
  return true;
}

/** remove a cache folder, first unlinking a node_modules junction in it so the removal never follows it */
function removeTree(dir, L) {
  const link = path.join(dir, 'game', 'node_modules');
  let st; try { st = fs.lstatSync(link); } catch { st = null; }
  if (st?.isSymbolicLink()) {
    try { fs.unlinkSync(link); } catch { try { fs.rmdirSync(link); } catch { /* checked below */ } }
    if (fs.existsSync(link)) { L.warn(`warning: could not remove the node_modules link in ${dir}; left it in place`); return; }
  }
  fs.rmSync(dir, { recursive: true, force: true });
}

/** Builds the packs and the game and runs the check. Returns { pass, outDir, body, gpu, desc }; never posts anything. */
export function runCheck(ctx) {
  const { repo, git, L, SHA, BASE, TOOLS, BASH, cache, game, GAME_SHA } = ctx;
  const posix = (p) => p.split(path.sep).join('/');
  // Windows' own bsdtar: Git Bash's GNU tar reads `C:` in a path as a remote host
  const winTar = process.platform === 'win32' && path.join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'tar.exe');
  const TAR = winTar && fs.existsSync(winTar) ? winTar : 'tar';
  /** `paths` of <sha> in the clone <from>, with LF line endings (as CI's checkout), unpacked into <dir> */
  function unpack(from, sha, dir, paths) {
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    const tarFile = path.join(dir, 'src.tar');
    out('git', ['-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive', '--format=tar', '-o', tarFile, sha, ...paths], { cwd: from });
    out(TAR, ['-xf', tarFile, '-C', dir]);
    fs.rmSync(tarFile);
  }

  // ---- synthetic packs -----------------------------------------------------------------------------------
  /** the synth key of <sha>'s pipeline/ as CI computes it: synth_key.sh on an LF copy */
  function synthKey(sha) {
    const src = path.join(cache, 'src', sha);
    if (!fs.existsSync(path.join(src, '.done'))) {
      unpack(repo, sha, src, ['pipeline']);
      fs.writeFileSync(path.join(src, '.done'), '');
    }
    return { key: out(BASH, ['tools/ci/synth_key.sh', posix(path.join(src, 'pipeline'))], { cwd: repo }), src };
  }
  /** the packs folder (packs/synth plus index.json) for a synth key, built once and kept in the cache */
  function synthPacks({ key, src }) {
    const dir = path.join(cache, 'synth', key);
    if (!fs.existsSync(path.join(dir, '.done'))) {
      L.step(`building the synthetic pack ${key} (about 2 minutes)`);
      fs.rmSync(dir, { recursive: true, force: true });
      fs.mkdirSync(dir, { recursive: true });
      if (L.run(PYTHON, [path.join(src, 'pipeline', 'synth_pack.py'), path.join(dir, 'synth')]) !== 0) die('synth_pack.py failed');
      fs.writeFileSync(path.join(dir, 'index.json'), '{"packs":["synth"]}\n');
      fs.writeFileSync(path.join(dir, '.done'), '');
    }
    return dir;
  }
  const synthBase = synthKey(BASE), synthHead = synthKey(SHA);
  const packsBase = synthPacks(synthBase), packsHead = synthPacks(synthHead);

  // ---- the game's main, unpacked and built once per game commit ----------------------------------------
  const gamesDir = path.join(cache, 'game');
  const gameRoot = path.join(gamesDir, GAME_SHA.slice(0, 12));
  const gameDir = path.join(gameRoot, 'game');
  if (!fs.existsSync(path.join(gameRoot, '.done'))) {
    if (fs.existsSync(gameRoot)) removeTree(gameRoot, L);
    L.step(`unpacking the game's main ${GAME_SHA.slice(0, 12)}`);
    unpack(game, GAME_SHA, gameRoot, ['game', 'tools/ci']);
    const lock = fs.readFileSync(path.join(gameDir, 'package-lock.json'));
    const cloneGame = path.join(game, 'game');
    if (installedMatches(cloneGame, lock)) {
      fs.symlinkSync(fs.realpathSync(path.join(cloneGame, 'node_modules')), path.join(gameDir, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
    } else {
      L.step(`npm ci for the game at ${GAME_SHA.slice(0, 12)} (the game clone's node_modules differs from its lockfile)`);
      if (L.run('npm', ['ci'], { cwd: gameDir, shell: process.platform === 'win32' }) !== 0) die(`npm ci failed for the game at ${GAME_SHA.slice(0, 12)}`);
    }
    L.step(`vite build of the game at ${GAME_SHA.slice(0, 12)}`);
    if (L.run(process.execPath, [path.join('node_modules', 'vite', 'bin', 'vite.js'), 'build'], { cwd: gameDir }) !== 0) die(`vite build failed for the game at ${GAME_SHA.slice(0, 12)}`);
    fs.writeFileSync(path.join(gameRoot, '.done'), new Date().toISOString());
  }
  // keep the newest few game builds
  const builds = fs.readdirSync(gamesDir).map((n) => path.join(gamesDir, n))
    .filter((p) => p !== gameRoot && fs.existsSync(path.join(p, '.done')))
    .sort((a, b) => fs.statSync(path.join(b, '.done')).mtimeMs - fs.statSync(path.join(a, '.done')).mtimeMs);
  for (const old of builds.slice(KEEP_GAME_BUILDS - 1)) removeTree(old, L);

  // ---- render, as the CI job does: the game's cishot.mjs on both packs ------------------------------------
  const runDir = path.join(cache, 'runs', SHA.slice(0, 12));
  const outDir = path.join(runDir, 'out');
  fs.rmSync(outDir, { recursive: true, force: true });
  const env = { ...ENV };
  for (const k of ['SHOT_QUERY', 'SHOT_CPU', 'SHOT_HEADED', 'SHOT_DIST']) delete env[k];
  const cishot = path.join(gameDir, 'tools', 'cishot.mjs');
  L.step('cishot.mjs on the merge base\'s pack (before)');
  L.run(process.execPath, [cishot, 'synth', path.join(outDir, 'before'), SHOT_FLAG], { cwd: gameDir, env: { ...env, SHOT_PACKS: packsBase } });
  L.step(`cishot.mjs on ${SHA.slice(0, 12)}'s pack (after)`);
  const after = L.run(process.execPath, [cishot, 'synth', path.join(outDir, 'after'), SHOT_FLAG], { cwd: gameDir, env: { ...env, SHOT_PACKS: packsHead } });

  L.step('render_report.py');
  const reportDir = path.join(outDir, 'report');
  const rep = L.run(PYTHON, [path.join(gameRoot, 'tools', 'ci', 'render_report.py'), path.join(outDir, 'before'), path.join(outDir, 'after'), reportDir]);
  const reportPath = path.join(reportDir, 'report.md');
  if (fs.existsSync(reportPath)) {
    const same = synthBase.key === synthHead.key ? ['--same-pack'] : [];
    const owner = ctx.owner;
    L.run(PYTHON, [path.join(repo, 'tools', 'ci', 'render_note.py'), reportPath, '--game-repo', `${owner}/${GAME_NAME}`, '--game-sha', GAME_SHA, ...same]);
  }
  if (after !== 0 || rep !== 0 || !fs.existsSync(reportPath)) {
    return { pass: false, outDir, reportPath: fs.existsSync(reportPath) ? reportPath : null,
      why: after !== 0 ? 'cishot on the commit\'s pack: shader message, page error or crash' : 'over budget (see the report)' };
  }
  const gpu = JSON.parse(fs.readFileSync(path.join(outDir, 'after', 'stats.json'), 'utf8')).gpu ?? 'unknown GPU';
  const lines = fs.readFileSync(reportPath, 'utf8').split('\n');
  lines.splice(2, 0, '', `**Run locally** on \`${os.hostname()}\` (\`${gpu}\`) with \`tools/ci/local_render_budgets.mjs\` or the pre-push hook: after is ${SHA}, before is the merge base ${BASE}. CI skips its own \`render-budgets\` run for this commit; a new push, a new merge base, a change to the tools, a new commit on the game's main or a \`stills\` request runs it again.`);
  const body = path.join(reportDir, 'comment.md');
  fs.writeFileSync(body, lines.join('\n'));
  return { pass: true, outDir, body, gpu, desc: `passed base=${BASE} tools=${TOOLS} synth=${synthHead.key} game=${GAME_SHA.slice(0, 12)}` };
}

/** The `render-budgets/local` status (first: CI's job reads it about 30 s after a push), then the PR comment. */
export function post({ repo, sha, prNumber, prUrl, owner, desc, body }) {
  out('gh', ['api', `repos/{owner}/{repo}/statuses/${sha}`, '-f', 'state=success', '-f', `context=${CONTEXT}`, '-f', `description=${desc}`, '-f', `target_url=${prUrl}`], { cwd: repo });
  const ids = out('gh', ['api', `repos/{owner}/{repo}/issues/${prNumber}/comments?per_page=100`, '--paginate', '--jq',
    `.[] | select((.user.login == "github-actions[bot]" or .user.login == "${owner}") and (.body | startswith("${MARKER}"))) | .id`], { cwd: repo });
  const id = ids.split('\n').filter(Boolean).pop();
  const patched = id && tryOut('gh', ['api', '-X', 'PATCH', `repos/{owner}/{repo}/issues/comments/${id}`, '-F', `body=@${body}`, '--jq', '.html_url'], { cwd: repo });
  return patched || out('gh', ['api', `repos/{owner}/{repo}/issues/${prNumber}/comments`, '-F', `body=@${body}`, '--jq', '.html_url'], { cwd: repo });
}
