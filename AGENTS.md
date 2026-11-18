# Agent Rules

Guidance for AI agents working in this repository. Detailed rules live in
`.cursor/rules/` - follow all three:

1. **TDD by default** (`.cursor/rules/tdd-default.mdc`)
   Every change to `app/` starts with a failing test. Run `make test` before
   declaring done. CI gates the production deploy on the suite.

2. **Security check before done** (`.cursor/rules/security-check.mdc`)
   This repo deploys straight to a live server via a self-hosted runner.
   No secrets in code/history, new Flask routes require auth, never widen
   sudo or disable host key checking.

3. **Documentation updates with code** (`.cursor/rules/docs-update.mdc`)
   Update `README.md`, `Makefile` help text, `inventory.yml` comments, and
   `docs/` in the same commit as behavior changes. Stale docs are a bug.

## Repo quick facts

- **Stack**: Flask + SQLite app (`app/`), plain static HTML site (`website/`),
  Ansible playbooks (`playbooks/`), GitHub Actions CI (`.github/workflows/`).
- **Deploy**: push to `main` triggers tests on GitHub-hosted runners, then the
  existing playbooks run on the self-hosted runner (gym-server) with a local
  connection. Ansible remains the deploy engine.
- **One-command ops**: see `make help` - all targets are thin wrappers around
  playbooks/scripts.
- **No build step** for `website/` - files deploy as-is.
