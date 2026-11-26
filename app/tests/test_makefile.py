"""Guard tests for the Makefile / manage.sh entrypoints.

These keep the 'easy Ansible process' easy: if someone renames a
playbook or breaks a wrapper, CI fails instead of a user discovering
it on deploy day.

Agent sandboxes block make's exec of /bin/sh, so the two tests whose
recipes make actually executes would fail spuriously there (see issue
#9). An import-time probe detects that environment failure and skips
only those tests with a documented reason; on CI the guard is disabled
entirely (a probe failure there fails the tests loudly), and a genuine
Makefile error always stays fail-closed.
"""
import os
import subprocess
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SKIP_REASON = (
    "make cannot execute recipes in this environment (agent sandbox "
    "blocks exec of /bin/sh); Makefile guard tests run in CI"
)

# The skip exists only for agent sandboxes. On CI runners it must never
# fire: a probe failure there must fail the tests, not silently weaken
# the tests gate (see AGENTS.md: never delete or weaken a test).
_ON_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _probe_make_recipes():
    """Check whether make can exec a recipe shell here.

    Runs a minimal makefile whose recipe spawns a shell (`make --version`
    alone would not catch it). Returns (works, detail). Only environment
    failures (make unexecutable, exec of the recipe shell blocked, or an
    unusable temp dir) return works=False; a missing make binary or a
    genuine makefile error returns works=True so the guard tests fail
    loudly instead of skipping.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            probe_mk = os.path.join(tmp, "probe.mk")
            with open(probe_mk, "w") as fh:
                fh.write("probe:\n\t@true\n")
            # Pin an English (C) locale: make renders the recipe shell's
            # exec failure via strerror(), which is localized under a
            # non-English locale and would defeat the string match below.
            r = subprocess.run(
                ["make", "-f", probe_mk, "probe"],
                capture_output=True, text=True,
                env={
                    **os.environ,
                    "LC_ALL": "C",
                    "LC_MESSAGES": "C",
                    "LANGUAGE": "",
                },
            )
    except FileNotFoundError as exc:
        # make simply not installed: fail loudly (the guard tests raise
        # the same error when they invoke make) rather than skipping and
        # silently losing Makefile guard coverage.
        return True, f"make not found: {exc}"
    except OSError as exc:  # PermissionError is an OSError subclass
        return False, f"{type(exc).__name__}: {exc}"
    if r.returncode == 0:
        return True, ""
    output = (r.stderr or "") + (r.stdout or "")
    if "Operation not permitted" in output or "Permission denied" in output:
        return False, f"exit {r.returncode}: {output.strip()}"
    return True, output.strip()  # genuine make/makefile error — do not skip


_MAKE_RECIPES_WORK, _PROBE_DETAIL = _probe_make_recipes()

# Skip guard for tests whose recipes make actually executes. Dry-run
# (`make -n`) and bash-syntax tests never exec a shell and stay active.
# Never skips on CI: there the recipe tests must run whatever the probe
# says, so a broken runner fails the suite instead of hiding behind skips.
_requires_make_recipes = pytest.mark.skipif(
    not _MAKE_RECIPES_WORK and not _ON_CI,
    reason=_SKIP_REASON + (f" [{_PROBE_DETAIL}]" if _PROBE_DETAIL else ""),
)


def _make(*args):
    return subprocess.run(
        ["make", *args], cwd=PROJECT_ROOT, capture_output=True, text=True
    )


@_requires_make_recipes
def test_makefile_exists_and_lists_targets():
    r = _make("help")
    assert r.returncode == 0, r.stderr
    for target in ("deploy-app", "backup", "rollback", "check", "test"):
        assert target in r.stdout


@_requires_make_recipes
def test_make_ansible_check_passes():
    assert _make("ansible-check").returncode == 0


def test_make_deploy_app_invokes_the_playbook():
    r = _make("-n", "deploy-app")
    assert r.returncode == 0
    assert "playbooks/deploy-app.yml" in r.stdout


def test_make_backup_and_rollback_invoke_playbooks():
    assert "playbooks/backup.yml" in _make("-n", "backup").stdout
    assert "playbooks/rollback.yml" in _make("-n", "rollback").stdout


def test_make_test_runs_python_suite():
    r = _make("-n", "test")
    assert "run-python-tests.sh" in r.stdout


def test_manage_sh_supports_app_commands():
    r = subprocess.run(
        ["bash", "-n", "scripts/manage.sh"], cwd=PROJECT_ROOT,
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr  # valid bash
    content = open(os.path.join(PROJECT_ROOT, "scripts", "manage.sh")).read()
    for cmd in ('"app"', "deploy-app.yml"):
        assert cmd in content, cmd
