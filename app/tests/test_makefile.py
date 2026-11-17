"""Guard tests for the Makefile / manage.sh entrypoints.

These keep the 'easy Ansible process' easy: if someone renames a
playbook or breaks a wrapper, CI fails instead of a user discovering
it on deploy day.
"""
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make(*args):
    return subprocess.run(
        ["make", *args], cwd=PROJECT_ROOT, capture_output=True, text=True
    )


def test_makefile_exists_and_lists_targets():
    r = _make("help")
    assert r.returncode == 0, r.stderr
    for target in ("deploy-app", "backup", "rollback", "check", "test"):
        assert target in r.stdout


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
