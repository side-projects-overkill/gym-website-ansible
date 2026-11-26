# Agent Rules

Guidance for AI agents working in this repository. These rules always apply.

## 1. TDD by default

Test-first is the default for any change to `app/` (Flask app, Python). Do not
write implementation code without a failing test that justifies it.

### Workflow

1. **Red**: write a failing test in `app/tests/` that captures the new behavior or bug.
2. **Green**: write the minimal code in `app/gymapp/` to make it pass.
3. **Refactor**: clean up while keeping the suite green.
4. Run the suite before declaring done: `./scripts/run-python-tests.sh` (or `make test`).

### Rules

- Bug fixes start with a regression test that reproduces the bug.
- New features start with tests describing the expected behavior.
- Never delete or weaken a test to make code pass; if a test is wrong, explain why and fix it.
- Tests must not require the server, network, or real credentials - use fixtures/mocks
  (see `app/tests/conftest.py`).
- Known sandbox limitation: agent sandboxes block make's exec of /bin/sh, so the
  Makefile guard tests that execute recipes skip with a stated reason - treat that
  clean skip as expected; CI on GitHub-hosted runners runs them fully.
- Ansible playbooks are verified with `make ansible-check` (syntax) and, where
  possible, idempotent re-run behavior rather than unit tests.

### CI Contract

`.github/workflows/tests.yml` runs the full suite on GitHub-hosted runners and
`deploy.yml` gates the self-hosted deploy on tests passing. Never bypass or mark
the tests job as non-blocking.

Merges to `main` also wait for the fullsend review check (`dispatch / Review`
from `.github/workflows/fullsend.yaml`) to complete successfully - the review
gate is the same class of protection as the tests gate, and every merge
deploys straight to the live gym-server. Do not merge while the review run is
queued, in progress, or has failed. Until the required status check
`dispatch / Review` is configured in branch protection for `main`, this rule
is advisory only - verify the review run has a verdict before merging.

## 2. Security check before done

This repo deploys directly to a live server (gym-server, 192.168.1.11) via a
self-hosted GitHub Actions runner, so insecure changes go straight to production.
Run a security pass before declaring any change complete.

### Secrets

- Never commit secrets, tokens, or passwords. Registration/one-time tokens
  (e.g. GitHub runner tokens) are consumed at use-time and must not appear in
  code, docs, commit messages, or chat logs.
- Admin passwords are passed via `-e admin_password=...` or auto-generated;
  they are never stored in the repo or inventory.
- The Telegram helper owns the bot token; this app talks only to its REST API.
  Never add a bot token, webhook, or direct Telegram Bot API call here.

### Flask app (`app/gymapp/`)

- All routes require auth unless explicitly public; new routes default to
  `@login_required` (or equivalent) - justify any exception.
- Validate and type-check all user input; never trust form/query data.
- Keep multi-user isolation: per-user data dirs must not be enumerable or
  cross-accessible by another user's session.

### Ansible / CI

- Playbooks run as root on the server - treat every task as privileged.
  No `curl | bash` from untrusted URLs, no wide-open file modes.
- The self-hosted runner user (`runner`) has scoped sudo (`/usr/bin/ansible-playbook`
  only, via `/etc/sudoers.d/github-runner`). Do not widen this without an explicit
  security rationale.
- Do not disable `host_key_checking`, add `NOPASSWD: ALL`, or run the runner as root.

### Checklist before finishing

- [ ] No new secrets in code, inventory, docs, or git history
- [ ] New routes are authenticated; inputs validated
- [ ] No privilege or sudo scope widened
- [ ] Dependencies pinned or constrained (`requirements*.txt`, dnf packages)

## 3. Documentation updates with code

Docs are part of the change, not a follow-up. If behavior, commands, or
infrastructure change, update the docs in the same commit.

### What to update

- **New/changed command or workflow?** Update `README.md` and the relevant
  `make` target help text in `Makefile` (targets are thin wrappers - the help
  output is the user-facing cheat sheet).
- **New playbook or playbook task?** Update `README.md` deployment docs and,
  if the task is user-visible, `docs/`.
- **New/changed app feature?** Update `README.md` feature list and
  `docs/` where behavior is described.
- **CI/workflow change?** Update `.github/workflows/` docs references in
  `README.md` (badges, pipeline description).
- **Config/inventory vars added?** Document them in `inventory.yml` comments
  and `README.md` configuration section.

### Rules

- Stale docs are a bug: if you find documentation that no longer matches
  reality, fix it in the same commit or note it explicitly in the summary.
- Prefer concrete, copy-pasteable commands over prose descriptions.
- Every public-facing page (`website/*.html`) is self-contained static HTML -
  no build step; note this in docs rather than introducing tooling.
- The deploy flow is: tests (GitHub-hosted) then Ansible playbooks via the
  self-hosted runner (`-c local`). Keep diagrams/notes in `docs/` aligned
  with this architecture when it changes.

### Checklist before finishing

- [ ] README.md reflects new/changed commands and features
- [ ] Makefile help text is accurate
- [ ] New inventory vars are commented
- [ ] docs/ entries updated if architecture changed

## Repo quick facts

- **Stack**: Flask + SQLite app (`app/`), plain static HTML site (`website/`),
  Ansible playbooks (`playbooks/`), GitHub Actions CI (`.github/workflows/`).
- **Deploy**: push to `main` triggers tests on GitHub-hosted runners, then the
  existing playbooks run on the self-hosted runner (gym-server) with a local
  connection. Ansible remains the deploy engine.
- **One-command ops**: see `make help` - all targets are thin wrappers around
  playbooks/scripts.
- **No build step** for `website/` - files deploy as-is.
