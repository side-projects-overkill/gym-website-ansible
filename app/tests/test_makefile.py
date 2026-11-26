"""Guard tests for the Makefile / manage.sh entrypoints.

These keep the 'easy Ansible process' easy: if someone renames a
playbook or breaks a wrapper, CI fails instead of a user discovering
it on deploy day.

Agent sandboxes block make's exec of /bin/sh, so the two tests whose
recipes make actually executes would fail spuriously there (see issue
#9). An import-time probe detects that environment failure and skips
only those tests with a documented reason; on CI (and whenever a
Makefile error is genuine) everything stays fully active.
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


def _probe_make_recipes():
    """Check whether make can exec a recipe shell here.

    Runs a minimal makefile whose recipe spawns a shell (`make --version`
    alone would not catch it). Returns (works, detail). Only environment
    failures (make missing/unexecutable, or exec of the recipe shell
    blocked) return works=False; a genuine makefile error returns
    works=True so the guard tests fail loudly instead of skipping.
    """
    with tempfile.TemporaryDirectory() as tmp:
        probe_mk = os.path.join(tmp, "probe.mk")
        with open(probe_mk, "w") as fh:
            fh.write("probe:\n\t@true\n")
        try:
            r = subprocess.run(
                ["make", "-f", probe_mk, "probe"],
                capture_output=True, text=True,
            )
        except (PermissionError, OSError) as exc:
            return False, f"{type(exc).__name__}: {exc}"
    if r.returncode == 0:
        return True, ""
    output = (r.stderr or "") + (r.stdout or "")
    if "Operation not permitted" in output or "Permission denied" in output:
        return False, output.strip()
    return True, output.strip()  # genuine make/makefile error — do not skip


_MAKE_RECIPES_WORK, _PROBE_DETAIL = _probe_make_recipes()

# Skip guard for tests whose recipes make actually executes. Dry-run
# (`make -n`) and bash-syntax tests never exec a shell and stay active.
requires_make_recipes = pytest.mark.skipif(
    not _MAKE_RECIPES_WORK,
    reason=_SKIP_REASON + (f" [{_PROBE_DETAIL}]" if _PROBE_DETAIL else ""),
)


def _make(*args):
    return subprocess.run(
        ["make", *args], cwd=PROJECT_ROOT, capture_output=True, text=True
    )


@requires_make_recipes
def test_makefile_exists_and_lists_targets():
    r = _make("help")
    assert r.returncode == 0, r.stderr
    for target in ("deploy-app", "backup", "rollback", "check", "test"):
        assert target in r.stdout


@requires_make_recipes
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
