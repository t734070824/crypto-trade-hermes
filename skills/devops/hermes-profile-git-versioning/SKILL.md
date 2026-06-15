---
name: hermes-profile-git-versioning
description: Version-control a Hermes profile directory safely with selective .gitignore rules, preserving only intended profile artifacts and user-created skills.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Hermes, Git, profile, version-control, dotfiles, skills]
    related_skills: [github-pr-workflow, hermes-agent]
---

# Hermes Profile Git Versioning

Use this when a user wants to turn an active Hermes profile directory into a Git repository, push it to GitHub, or constrain which profile files are committed.

## Core principle

A Hermes profile contains live runtime state, logs, databases, caches, credentials, and bundled/hub-installed skills. Do **not** blindly `git add .`. Build an allowlist-style `.gitignore`, then verify with `git status --ignored` and `git check-ignore` before committing.

## Workflow

1. Confirm repository root and remote intent.
   - Use the active profile path as root only if the user explicitly wants that.
   - Prefer SSH remotes when the user says SSH keys are configured.

2. Inspect existing files/directories before writing ignore rules.
   - Identify root-level documents the user wants tracked, e.g. `SOUL.md` vs `soul.md`.
   - Identify directories that may be empty; Git will not commit empty directories unless a placeholder is added.

3. Use an allowlist `.gitignore` pattern.

```gitignore
# Default deny everything at repository root
/*

# Keep repo metadata/rules and explicitly requested root files
!/.gitignore
!/config.yaml
!/SOUL.md
!/soul.md

# Requested profile subdirectories: commit all contents
!/home/
!/home/**
!/hooks/
!/hooks/**
!/memories/
!/memories/**
!/cron/
!/cron/**
!/plan/
!/plan/**
!/plans/
!/plans/**
!/scripts/
!/scripts/**
!/tests/
!/tests/**

# Generated Python caches under allowed script/test directories.
**/__pycache__/
*.py[cod]

# Allow skills/ as a container so newly-created skill folders can be committed
!/skills/
!/skills/**/

# Then explicitly ignore existing/bundled skill folders and skill metadata files
/skills/.bundled_manifest
/skills/.usage.json
/skills/.usage.json.lock
/skills/.hub/
/skills/<existing-category-or-skill>/
```

4. For `skills/`, treat existing skills as a denylist snapshot.
   - Enumerate all existing skill folders at generation time and add explicit ignore entries for each.
   - Keep `!/skills/**/` so future newly-created skill folders remain discoverable and trackable.
   - Ignore skill metadata such as `.bundled_manifest`, `.usage.json`, and lock files.

5. Verify ignore behavior before committing.

```bash
git status --short --ignored
git check-ignore -v .env || true
git check-ignore -v skills/<existing-skill>/SKILL.md || true
git check-ignore -v skills/<future-skill>/SKILL.md || true
git check-ignore -v SOUL.md || true
git check-ignore -v config.yaml || true
git check-ignore -v plans/example.md || true
git check-ignore -v cron/example.txt || true
```

Expected:
- credentials/logs/db/caches are ignored;
- explicitly requested root docs are not ignored;
- requested directories are not ignored;
- existing skills are ignored;
- hypothetical future skill folders are not ignored.

6. Commit only after checking staged files.

```bash
git add -A
git status --short
git commit -m "chore: add repository ignore rules"
git push -u origin main
```

7. After any tool action that may change files in this profile, run a repository status check before replying.

This includes `memory`, `skill_manage`, `write_file`, `patch`, generated cron/home/hooks files, or commands that create/update files. Do **not** narrow this to `memories/` only: user corrections in this repo showed that `skill_manage` can update newly-created tracked skill folders at the same time as memory changes.

```bash
git status --short --branch
```

If there are changes allowed by the repository policy, commit and push them before the final reply:

```bash
git add -A
git status --short
# verify the staged list contains only intended allowlisted paths:
#   .gitignore, config.yaml, SOUL.md/soul.md, home/**, hooks/**,
#   memories/**, cron/**, plan/**, plans/**,
#   and newly-created skills/** folders that are not ignored.
git commit -m "chore: update profile state"
git push
```

Config note: in the crypto-trade-hermes profile, `config.yaml` is explicitly allowlisted and should be committed/pushed when intentionally changed, while `.env`, logs, databases, sessions, caches, pid/lock files, and live gateway state remain ignored. If unexpected files appear, inspect with `git status --short --ignored` and `git check-ignore -v <path>`; fix `.gitignore` or ask before committing. The user's default for git flows is to push after committing.

If Git identity is missing, set repository-local identity, not global, unless the user requests a global identity.

```bash
git config user.name "Hermes Agent"
git config user.email "hermes-agent@users.noreply.github.com"
```

## Pitfalls

- File case matters: if the user says `soul.md` but the directory contains `SOUL.md`, report that and track the real file unless they ask for a rename.
- Empty directories are not pushed by Git. Report empty `home/` or `hooks/` rather than claiming they were committed.
- `!/skills/**/` alone can make many existing skill files visible unless the existing skill folders are explicitly ignored afterward.
- Do not commit `.env`, `state.db`, `state.db-wal`, `state.db-shm`, logs, sessions, caches, pid/lock files, or live gateway state unless the user explicitly asks.

## References

- `references/selective-profile-repo.md` — example policy and verification notes from a profile-root repository setup.
- `references/profile-config-visibility.md` — Hermes profile config keys for Telegram/gateway real-time tool progress and context-usage footer, plus the note that ignored `config.yaml` changes are local rather than pushed.
- `references/profile-source-test-allowlist.md` — how to safely add project `scripts/` and `tests/` directories to a profile-root repository, including Python cache and Skills Hub cache ignore rules.
