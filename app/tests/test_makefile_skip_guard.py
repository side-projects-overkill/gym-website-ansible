"""Tests for the environment-aware skip guard in test_makefile.py.

Agent sandboxes block make's exec of /bin/sh, which used to fail the two
Makefile guard tests that execute recipes. The guard probes whether make
can actually run a recipe and, only when that is an environment failure,
skips those tests with a documented reason. Everything must stay active
on CI runners, and a genuinely broken Makefile must still fail loudly
instead of silently skipping (see AGENTS.md: never weaken a test).
"""
import importlib.util
import os
import subprocess

TEST_MAKEFILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_makefile.py"
)

# Tests whose recipes make actually executes (make help / make ansible-check).
RECIPE_TESTS = (
    "test_makefile_exists_and_lists_targets",
    "test_make_ansible_check_passes",
)
# Tests that only dry-run (-n) make or never invoke it: they must never
# be weakened by the guard.
NON_RECIPE_TESTS = (
    "test_make_deploy_app_invokes_the_playbook",
    "test_make_backup_and_rollback_invoke_playbooks",
    "test_make_test_runs_python_suite",
    "test_manage_sh_supports_app_commands",
)


def _load_test_makefile():
    """Load a fresh copy of test_makefile.py, running its import-time probe."""
    spec = importlib.util.spec_from_file_location(
        "test_makefile_under_probe", TEST_MAKEFILE
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _skipif_mark(func):
    """Return the skipif mark on a test function, or None."""
    for mark in getattr(func, "pytestmark", []):
        if mark.name == "skipif":
            return mark
    return None


def _patch_run(monkeypatch, result=None, error=None):
    """Replace subprocess.run for the duration of one module load."""

    def fake_run(cmd, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)


def _assume_not_on_ci(monkeypatch):
    """Clear CI markers so the sandbox skip path is the one under test."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


def test_recipe_tests_skip_when_make_cannot_exec_shell(monkeypatch):
    """The sandbox failure mode ('Operation not permitted') skips with a reason."""
    _assume_not_on_ci(monkeypatch)
    _patch_run(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=["make"],
            returncode=127,
            stdout="",
            stderr=(
                "make: /bin/sh: Operation not permitted\n"
                "make: *** [probe.mk:1: probe] Error 127\n"
            ),
        ),
    )
    mod = _load_test_makefile()
    for name in RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is not None, f"{name} lacks the environment skipif guard"
        assert mark.args[0] is True, f"{name} should skip when make cannot exec"
        reason = mark.kwargs.get("reason", "")
        assert "CI" in reason, "skip reason must say the tests still run in CI"


def test_recipe_tests_skip_when_make_cannot_be_executed(monkeypatch):
    """A missing/unexecutable make binary is also an environment failure."""
    _assume_not_on_ci(monkeypatch)
    _patch_run(
        monkeypatch, error=PermissionError(13, "Permission denied", "make")
    )
    mod = _load_test_makefile()
    for name in RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is not None, f"{name} lacks the environment skipif guard"
        assert mark.args[0] is True, f"{name} should skip when make cannot run"


def test_nothing_skips_when_recipes_execute(monkeypatch):
    """A working make keeps every test active."""
    _patch_run(
        monkeypatch,
        result=subprocess.CompletedProcess(args=["make"], returncode=0),
    )
    mod = _load_test_makefile()
    for name in RECIPE_TESTS + NON_RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is None or mark.args[0] is False, (
            f"{name} must stay active when make works"
        )


def test_nothing_skips_on_genuine_makefile_error(monkeypatch):
    """A real makefile error must fail the tests, not skip them."""
    _patch_run(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=["make"],
            returncode=2,
            stdout="",
            stderr="probe.mk:1: *** missing separator.  Stop.\n",
        ),
    )
    mod = _load_test_makefile()
    for name in RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is None or mark.args[0] is False, (
            f"{name} must stay active so genuine Makefile errors fail loudly"
        )


def test_probe_failure_on_ci_fails_loud_instead_of_skipping(monkeypatch):
    """On CI runners the guard must never skip the recipe tests.

    The skip exists only for agent sandboxes; if the probe ever fails on
    a CI runner (misconfigured image, broken make), the tests must run
    and fail loudly rather than silently weaken the tests gate.
    """
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    _patch_run(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=["make"],
            returncode=127,
            stdout="",
            stderr=(
                "make: /bin/sh: Operation not permitted\n"
                "make: *** [probe.mk:1: probe] Error 127\n"
            ),
        ),
    )
    mod = _load_test_makefile()
    for name in RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is None or mark.args[0] is False, (
            f"{name} must stay active on CI so a probe failure fails loudly"
        )


def test_non_recipe_tests_never_guarded_by_guard(monkeypatch):
    """Dry-run and bash -n tests keep running even when make is blocked."""
    _assume_not_on_ci(monkeypatch)
    _patch_run(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=["make"],
            returncode=127,
            stdout="",
            stderr="make: /bin/sh: Operation not permitted\n",
        ),
    )
    mod = _load_test_makefile()
    for name in NON_RECIPE_TESTS:
        mark = _skipif_mark(getattr(mod, name))
        assert mark is None or mark.args[0] is False, (
            f"{name} does not execute recipes and must never be skipped"
        )
