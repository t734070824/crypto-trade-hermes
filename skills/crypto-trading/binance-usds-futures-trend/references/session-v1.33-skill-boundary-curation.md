# Session v1.33 — Skill-library curation after cron boundary changes

## Trigger

Use this note after changing the operational boundary between deterministic `no_agent=true` script-owned cron jobs and `no_agent=false` agent-owned diagnostics/analysis jobs, or after compressing MEMORY/USER/SKILL content for this trading profile.

## Durable lesson

A cron ownership change is not complete when only `cron/jobs.json` and the main operational paragraph are updated. The Skill library itself can preserve stale architectural advice in:

- `## Common Pitfalls` entries;
- `## References` one-line descriptions;
- historical `references/session-*.md` notes;
- memory/profile preference statements.

If those stale notes still say “hourly must be one Skill-loaded agent cron” while the current design is script-owned, future agents may revert the intended boundary.

## Curation checklist

1. Patch the active cron definition first:
   - `testnet-agent-hourly`: `no_agent=true`, `skills: []`, `skill: null`, `script: "binance_usds_futures_testnet_hourly.sh"`, paused unless explicitly resumed.
   - `replay-diagnostics-daily`: `no_agent=false`, `script: null`, Skill loaded, read-only, paused unless explicitly resumed.
2. Patch the main `Operational cron pattern` section.
3. Search the whole Skill directory for stale phrases such as:
   - `single Skill-loaded agent cron should own`;
   - `one Skill-loaded agent cron owns`;
   - `one agent-type hourly cron owns`;
   - `script: null` paired with `testnet-agent-hourly`;
   - `only acceptable for deterministic evidence collectors`.
4. Patch stale reference files by marking older conclusions as superseded/refined, not by deleting useful history.
5. Patch `## References` descriptions so the index does not advertise the old boundary.
6. Update memory/profile preference statements if they encode the old topology.
7. Preserve durable trading constraints while compressing text. Do not drop:
   - `position_size` means target total exposure, not additive order size;
   - sizing depends on account margin/equity and stop-loss distance;
   - execution uses delta-only reconciliation;
   - `>=1h` interval constraint;
   - live/mainnet remains unauthorized.
8. Preserve executable CLI boundaries, not only prose. For strict testnet crons, keep both flags visible in the Skill when relevant:
   - `--base-url https://testnet.binancefuture.com` for public data reads;
   - `--testnet-base-url https://testnet.binancefuture.com` for signed broker endpoints.
9. Update frontmatter descriptions when capability language changes. If the body says the current code has a hardened testnet adapter, the description must not still say the code is “paper-only”.
10. Get independent review before commit/push; ask the reviewer to search for contradictions, missing constraints, and weakened prompt/CLI/code boundaries, not only inspect the latest diff. If the reviewer finds issues and you patch them, rerun review on the final diff.

## Reporting rule

In final reports, distinguish:

- the cron/job config change;
- the Skill/library consistency update;
- whether signed testnet execution was intentionally avoided;
- whether jobs stayed paused or were resumed;
- which validation and independent review passed before push.
