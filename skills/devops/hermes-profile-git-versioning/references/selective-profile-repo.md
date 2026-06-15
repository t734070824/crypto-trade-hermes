# Selective Hermes Profile Repository Policy

Session-derived example for a Hermes profile directory used directly as a Git root.

## User policy captured

Track only:

- root-level soul document (`SOUL.md` in the actual directory; user may type `soul.md`)
- all contents under:
  - `home/`
  - `hooks/`
  - `memories/`
  - `cron/`
- contents of newly-created folders under `skills/`

Do not track:

- existing skill folders present when the policy is generated
- runtime state (`state.db*`, gateway state, pid/lock files)
- credentials (`.env`)
- logs, sessions, caches, sandboxes, workspace artifacts
- bundled/hub skill metadata (`.bundled_manifest`, `.usage.json`, locks)

## Verification pattern

After generating `.gitignore`, run checks equivalent to:

```bash
git status --short --ignored

git check-ignore -v skills/github/github-pr-workflow/SKILL.md || echo 'NOT IGNORED'
git check-ignore -v skills/trading-binance/SKILL.md || echo 'NOT IGNORED'
git check-ignore -v .env || echo 'NOT IGNORED'
git check-ignore -v SOUL.md || echo 'NOT IGNORED'
git check-ignore -v cron/example.txt || echo 'NOT IGNORED'
```

Expected behavior:

- existing skill path prints a matching ignore rule;
- hypothetical future skill path prints `NOT IGNORED`;
- `.env` prints a matching ignore rule;
- `SOUL.md` and files under requested profile directories are not ignored.

## Reporting notes

When summarizing:

- mention if `home/` or `hooks/` are empty because Git will not push empty directories;
- mention if the requested lowercase filename differs from the actual uppercase file;
- include branch and commit hash after push verification.
