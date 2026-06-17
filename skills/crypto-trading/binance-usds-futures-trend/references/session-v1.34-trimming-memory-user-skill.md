# Trimming MEMORY / USER / SKILL together

Use this checklist when compressing profile memory and the governing Skill after a boundary change.

## Keep

- Durable trading invariants:
  - `>=1h` intervals only.
  - `position_size` means target total exposure, not additive order size.
  - sizing depends on account margin/equity and stop-loss distance.
  - execution reconciles `current_exposure` vs `desired_exposure` delta-only.
  - paper/testnet/live share strategy, state, risk, lifecycle, execution, and evidence interfaces.
  - live/mainnet remains unauthorized unless explicitly implemented and approved.
- Executable CLI boundaries:
  - strict testnet crons must keep both `--base-url https://testnet.binancefuture.com` and `--testnet-base-url https://testnet.binancefuture.com` visible when relevant.
- User preferences that belong in USER.md:
  - Chinese, concise replies.
  - time labels must show UTC or 北京时间（UTC+8）.
  - default push after git commits.
  - distinguish scheduled trigger, execution completion, and delivery time.
  - separate prompt text, CLI flags, and actual code execution.

## Remove or compress

- Duplicate statements about the same cron boundary.
- Historical version-by-version capability lists from the Skill body.
- Old references that advertise a superseded ownership model as the current one.
- Any frontmatter description that still says “paper-only” after the body documents a hardened testnet adapter.
- Repeated statements of the same user preference in both MEMORY and USER.

## Before pushing

1. Re-read the edited files.
2. Check for missing reference files.
3. Run diff whitespace checks.
4. Get independent review on the final diff.
5. Commit and push only after the review passes.
