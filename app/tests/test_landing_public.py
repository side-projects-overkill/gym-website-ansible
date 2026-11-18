"""The public landing page must be polished and reveal nothing internal
(no deployment, infrastructure, stack, or config details)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INTERNAL_WORDS = ["ansible", "deploy", "readme", "flask", "sqlite", "gunicorn",
                  "apache", "yaml", "192.168", "server", "github", "telegram"]


def _visible_text(html):
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html).lower()


def test_landing_reveals_nothing_internal(client):
    html = client.get("/").get_data(as_text=True)
    text = _visible_text(html)
    for word in INTERNAL_WORDS:
        assert word not in text, word
    assert "readme" not in html.lower()


def test_landing_has_preview_and_calls_to_action(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="landing-preview"' in html
    assert html.count('href="/register"') >= 2   # hero + closing CTA
    assert 'href="/login"' in html


def test_visitor_nav_is_minimal(client):
    html = client.get("/").get_data(as_text=True)
    nav = html.split('class="topnav"', 1)[1].split("</nav>", 1)[0]
    assert "Log in" in nav and "Get started" in nav
    assert len(re.findall(r"<a ", nav)) == 3     # brand, log in, get started


def test_apache_serves_no_static_files():
    conf = open(os.path.join(ROOT, "playbooks/templates/gymapp-httpd.conf.j2")).read()
    assert "readme" not in conf.lower()
    assert " !" not in conf      # no proxy exclusions -> nothing served from disk
    assert "ServerTokens Prod" in conf


def test_deploy_removes_legacy_public_files():
    playbook = open(os.path.join(ROOT, "playbooks/deploy-app.yml")).read()
    assert "readme.html" in playbook and "state: absent" in playbook
