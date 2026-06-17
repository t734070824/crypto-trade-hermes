# Session note: focused Skill/reference documentation push

Use this note when the user asks to push only Skill-library or `references/` changes from a Hermes profile repository.

Durable pattern:

1. Keep the commit scope narrow: staged paths should be limited to the intended `skills/**/SKILL.md` index changes and `skills/**/references/*.md` files.
2. Before review, inspect the staged diff for:
   - missing reference files that are indexed from `SKILL.md`;
   - weakened durable trading/runtime constraints;
   - accidental runtime state such as `cron/jobs.json`, `state/*`, logs, outputs, caches, or scheduler timestamps.
3. Run or request independent review on the exact staged diff that will be committed.
4. Commit and push only after review passes.
5. Immediately after push, check repository cleanliness again. Hermes scheduler activity can rewrite `cron/jobs.json` during the commit/push window; if the diff is pure runtime noise, restore it instead of creating a second noisy commit.

Pitfall: a successful docs-only push does not guarantee the working tree stayed clean. Always do the final post-push status check, especially in profiles with active cron jobs.
