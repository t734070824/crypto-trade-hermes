# Profile Repository Source/Test Allowlist Notes

Use this reference when a Hermes profile directory is also used as a lightweight project repository, not only as runtime profile state.

## When to broaden the allowlist

If the user asks to build project artifacts inside the profile root, commit small source/test directories explicitly instead of using broad `git add .` behavior.

Common allowlist additions:

```gitignore
!/scripts/
!/scripts/**
!/tests/
!/tests/**
```

Keep the allowlist narrow and explicit. Add other source directories only after the project actually needs them.

## Python cache pitfall

Once `scripts/` and `tests/` are allowlisted, Python runs may expose generated caches unless ignored explicitly:

```gitignore
# Generated Python caches under allowed script/test directories.
**/__pycache__/
*.py[cod]
```

Verify with:

```bash
git status --short --ignored -- scripts tests
git check-ignore -v tests/__pycache__ scripts/__pycache__ || true
```

Expected: source/test files are visible or tracked; `__pycache__/` and bytecode are ignored.

## Skills Hub cache pitfall

`hermes skills search` may create `skills/.hub/` cache files. Treat these as runtime/cache state, not project artifacts:

```gitignore
/skills/.hub/
```

Do not inspect internal Hermes cache files directly; use `skills_list`, `skill_view`, or `hermes skills search/inspect` instead.

## Commit discipline

Before committing a broadened allowlist, stage only intended artifacts and inspect the staged diff:

```bash
git add .gitignore scripts tests plans/<plan>.md skills/<new-skill>/
git status --short
git diff --cached --stat
```

Then run the relevant verification command before commit/push.
