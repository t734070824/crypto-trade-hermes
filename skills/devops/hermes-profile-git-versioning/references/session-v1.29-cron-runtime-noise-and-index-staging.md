# Session v1.29: Cron runtime noise and exact index staging

## What happened
When reviewing and committing `cron/jobs.json`, the scheduler rewrote runtime fields (`next_run_at`, `updated_at`) during the review/commit window and again after push.

## Durable lesson
- Do not treat scheduler-driven timestamp churn as a meaningful config change.
- If the tracked file is being rewritten by the scheduler while you are reviewing it, reconstruct the durable content from the intended semantic fields only (for cron jobs, typically prompt/script/no_agent/schedule/deliver/skills).
- Stage the normalized durable blob directly with `git update-index --cacheinfo` when necessary so runtime fields do not race back into the staged diff.
- After push, re-check `git status`; if the only remaining local change is scheduler noise, restore the worktree copy with `git checkout -- <file>` unless the user explicitly asked to preserve runtime state.

## Useful checks
- `git diff --cached --check`
- `git diff --cached -- <path>`
- `git status --short --branch`
