# Gym Website Deployment System

[![CI](https://github.com/side-projects-overkill/gym-website-ansible/actions/workflows/tests.yml/badge.svg)](https://github.com/side-projects-overkill/gym-website-ansible/actions/workflows/tests.yml)
[![Tests](https://img.shields.io/badge/tests-90%20passing-brightgreen)](app/tests)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](app/requirements-dev.txt)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey)](app/requirements.txt)
[![Ansible](https://img.shields.io/badge/ansible--core-2.16%2B-black)](playbooks/)

A simple, practical Ansible setup for deploying and managing a fitness website. Perfect for personal projects, small teams, or learning automation.

## What This Does

This system automates website deployment to a Linux server using Ansible. It handles backups, file permissions, and service management so you can focus on content instead of server administration.

The primary deployment target is now the **Gym Tracker app** (`app/`): a small Flask + SQLite site with an admin panel for editing your workout program (as YAML) and logging body metrics (weight, height, or anything else you want to track) over time. See [Gym Tracker App](#gym-tracker-app-dynamic-site--admin-panel) below. The older static-HTML playbooks (`deploy-local.yml`, `deploy-website.yml`, etc.) still work if you ever want to go back to a plain static site.

**Live Example**: [http://192.168.1.11](http://192.168.1.11) - Gym Tracker app (public workout page + `/admin` panel)

## Project Structure

```
gym-website-ansible/
├── ansible.cfg                 # Ansible configuration (points at inventory.yml)
├── inventory.yml               # Server settings (edit this first)
├── app/                         # Gym Tracker Flask app (primary deployment target)
│   ├── wsgi.py                  # gunicorn entry point
│   ├── manage.py                # Admin bootstrap CLI (used by Ansible)
│   ├── requirements.txt         # For local dev only (server uses dnf packages)
│   ├── config/gym.yml           # Seed/default workout config
│   └── gymapp/                  # Flask package (routes, db, templates, static)
├── playbooks/
│   ├── deploy-app.yml           # Deploy the Gym Tracker app (systemd + Apache proxy) - primary
│   ├── deploy-website.yml      # Deploy from Git repository (static HTML)
│   ├── deploy-quick.yml        # Git deploy, no backup (wraps deploy-website.yml)
│   ├── deploy-local.yml        # Deploy local website/index.html, with backup
│   ├── deploy-local-quick.yml  # Local deploy, no backup (wraps deploy-local.yml)
│   ├── deploy-tracker.yml      # Deploy website/gym-tracker.html as the main site
│   ├── backup.yml              # Create a manual backup
│   ├── rollback.yml            # Emergency restore from backup
│   ├── performance-test.yml    # Install & configure load-testing tools on the server
│   ├── templates/               # systemd unit + Apache proxy conf for the app
│   └── tests/
│       ├── test-playbooks.yml          # Comprehensive test suite
│       └── test-local-deploy-tasks.yml # Reusable tasks for local-deploy tests
├── website/                     # Static HTML fallback (used by the older playbooks)
│   ├── index.html              # Main site content (workout guide)
│   ├── gym-tracker.html        # Alternate SPA (workout tracker)
│   ├── readme.html             # HTML docs served at /readme.html
│   └── test-index.html         # Unused draft/alternate copy of index.html
├── scripts/
│   ├── manage.sh                    # Primary CLI for day-to-day operations
│   ├── deploy.sh                    # Lightweight deploy/backup/test wrapper
│   ├── run-tests.sh                 # Test runner (playbooks + connectivity)
│   ├── test-connectivity.sh         # Pre-flight connectivity diagnostics
│   ├── run-performance-tests.sh     # Orchestrates local + remote load tests
│   ├── local-performance-test.sh    # Load tests run from your machine
│   ├── monitor-resources.sh         # Local + remote resource monitoring
│   ├── test-backup-performance.sh   # Backup/restore/I-O benchmarking
│   └── deploy-manual.sh             # Historical note from a manual deployment
└── docs/
    ├── setup-deployment.md
    ├── sample-website-structure.md
    ├── DEPLOYMENT_STATUS.md
    ├── PERFORMANCE_BASELINE_REPORT.md
    ├── SCALING_RECOMMENDATIONS.md
    └── TESTING_SUMMARY.md
```

All commands below assume you run them from the repository root.

## Quick Setup

### The Easy Way (Make)

After the prerequisites below, everything is one command:

```bash
make help        # list everything you can do
make check       # pre-flight: tests + playbook syntax + server ping
make deploy      # deploy the Gym Tracker app
make status      # uptime, services, disk
make logs        # tail the app journal
make backup      # manual backup
make rollback    # emergency restore
```

Tip: on first deploy only, pass an admin password:
`make deploy EXTRA='-e admin_password=secret'` (omit it and a random one
is generated and printed once).

`scripts/manage.sh` remains available with the same operations plus
`app`, `app-status`, `app-logs`, `app-restart` commands.

### Prerequisites

1. **Install Ansible**:
   ```bash
   pip install ansible
   # or on macOS:
   brew install ansible
   ```

2. **Configure SSH access**:
   ```bash
   # Add to ~/.ssh/config:
   Host gym
     HostName 192.168.1.11
     User root
     StrictHostKeyChecking no
   
   # Test connection:
   ssh gym
   ```

3. **Clone and test**:
   ```bash
   git clone <this-repo>
   cd gym-website-ansible
   ansible gym-server -m ping  # Should return "pong"
   ```

## Basic Usage

### Deploy the Local Website

1. **Edit `website/index.html`** with your content.

2. **Deploy it**:
   ```bash
   ansible-playbook playbooks/deploy-local.yml
   ```

3. **Visit your site**: http://192.168.1.11

### Update Your Website

When you have changes:

```bash
# Edit your website/index.html file
vim website/index.html

# Deploy changes (with backup)
ansible-playbook playbooks/deploy-local.yml

# Quick deploy (no backup)
ansible-playbook playbooks/deploy-local-quick.yml
```

### Deploy from Git Repository

If you keep your website in Git:

```bash
# Edit inventory.yml to set your repository URL
vim inventory.yml

# Deploy from Git
ansible-playbook playbooks/deploy-website.yml

# Or quickly, without a backup
ansible-playbook playbooks/deploy-quick.yml
```

### Using the Management Script

`scripts/manage.sh` wraps the common playbooks into one CLI:

```bash
./scripts/manage.sh deploy https://github.com/user/gym-website.git
./scripts/manage.sh local              # Deploy website/index.html
./scripts/manage.sh local-quick        # Quick local deploy
./scripts/manage.sh status
./scripts/manage.sh rollback
./scripts/manage.sh help               # See all commands
```

## Gym Tracker App (Dynamic Site + Admin Panel)

`app/` is a small Flask + SQLite application that replaces the static HTML page with:

- A **public workout page** rendered from a YAML config (no code changes needed to update your program).
- An **admin panel** (`/admin`) to edit that YAML, protected by a login.
- A **body-metric tracker** (weight, height, body fat, or any custom metric you define) backed by SQLite, with history, a trend chart, and CSV export.

It runs behind the existing Apache server via `mod_proxy` (gunicorn listens on `127.0.0.1:8099`), so no new ports need to be opened. Routing:

- `/` and `/guide` - the static workout guide (`website/index.html`), served by Apache. It loads the app's `/static/style.css` and mirrors its nav, so guide and app share one theme.
- App route prefixes (`/login`, `/dashboard`, `/plan`, `/static`, ...) - proxied to the Flask app. The list lives in `app_route_prefixes` in `playbooks/deploy-app.yml`; add new top-level app routes there.

### Deploy / Update the App

```bash
# First deploy (also installs python3-flask/pyyaml/gunicorn via dnf,
# creates a dedicated 'gymapp' system user, and prints admin credentials once):
ansible-playbook playbooks/deploy-app.yml

# Every later deploy just syncs code + restarts the service.
# Your data (SQLite db, workout YAML, admin login) is untouched.
ansible-playbook playbooks/deploy-app.yml
```

On the very first run, the playbook creates the admin account and prints a random password to the console **once** - copy it immediately, it is never stored in this repo or logged anywhere else. You can also set your own on that first run:

```bash
ansible-playbook playbooks/deploy-app.yml -e admin_username=yourname -e admin_password='YourOwnPassword123'
```

If you ever lose the password, reset it directly on the server (this does not touch your workout config or tracked metrics):

```bash
ansible gym-server -m command -a \
  "python3 manage.py --data-dir /opt/gymapp/data set-admin --username admin --password 'NewPassword123' --force" \
  -a "chdir=/opt/gymapp/app"
```

### Using the App

1. Visit `http://192.168.1.11/` for the public workout page, or `http://192.168.1.11/foods` for the food guide (both public, no login needed).
2. Visit `http://192.168.1.11/admin/login` and sign in.
3. **Dashboard** (`/admin/`): the fastest way to log weight - a one-field "Log Today's Weight" form plus a trend chart, right at the top.
4. **Workout Config** (`/admin/config`): edit the YAML that defines your days/exercises. It's validated before saving, and every save keeps a timestamped backup (`/admin/config/backups`) you can restore from.
5. **Tracker** (`/admin/tracker`): log any metric (weight, height, waist, custom ones you add) with a date and optional notes; see a trend chart and full history; export everything as CSV.
6. **Food Guide** (`/admin/foods` to edit, `/foods` to view publicly): a curated list of high-volume, low-calorie-density foods (vegetables, fruits, lean proteins, soups, whole grains) grouped by category and sorted by calories per 100g - useful for eating filling meals while losing weight. Edit it the same way as the workout config (validated YAML, with backups).
7. **Metrics** (`/admin/metrics`): define new trackable metrics (key/label/unit) beyond the defaults (weight, height, body fat %, waist, chest, arm, resting heart rate).
8. **Account** (`/admin/password`): change your password.

### App Data & Portability

Everything the app persists lives under **`/opt/gymapp/data`** on the server:

```
/opt/gymapp/data/
├── gym.db           # SQLite: metric definitions + logged entries
├── gym.yml          # Your current workout config (YAML)
├── foods.yml         # Your current food guide config (YAML)
├── auth.json         # Admin username + password hash
├── secret_key.txt    # Session signing key
└── backups/          # Timestamped gym.yml / foods.yml backups
```

To move the whole app to another host, copy this one directory and re-run `deploy-app.yml` targeting the new host - that's it, by design (per the "simple as SQLite so it can move easily" goal).

```bash
# Backup/move example
ansible gym-server -m fetch -a "src=/opt/gymapp/data/gym.db dest=./backups/gym.db flat=yes"
```

### Reverting to the Static Site

The app's Apache config (`/etc/httpd/conf.d/gymapp.conf`) proxies *all* paths to the Flask app, so the old static files in `website/` are no longer served while it's active. To go back to a plain static site:

```bash
ansible gym-server -m file -a "path=/etc/httpd/conf.d/gymapp.conf state=absent"
ansible gym-server -m systemd -a "name=httpd state=restarted"
ansible-playbook playbooks/deploy-local.yml
```

## Common Tasks

### Check if Everything is Working
```bash
# Test connection
ansible gym-server -m ping

# Check website is accessible
curl -I http://192.168.1.11

# Check server status
ansible gym-server -m shell -a "systemctl status httpd && df -h"
```

### View Logs
```bash
# Recent website visits
ansible gym-server -m shell -a "tail -10 /var/log/httpd/access_log"

# Server errors
ansible gym-server -m shell -a "tail -10 /var/log/httpd/error_log"
```

### Backup and Restore
```bash
# Create backup
ansible-playbook playbooks/backup.yml

# List backups
ansible gym-server -m shell -a "ls -la /var/backups/website/"

# Emergency restore
ansible-playbook playbooks/rollback.yml
```

### Restart Web Server
```bash
ansible gym-server -m systemd -a "name=httpd state=restarted"
```

## Configuration

Edit `inventory.yml` to match your setup:

```yaml
all:
  hosts:
    gym-server:
      ansible_host: 192.168.1.11    # Your server IP
      ansible_user: root             # SSH user
  vars:
    git_repo_url: "https://github.com/your-username/your-website.git"
    web_root: "/var/www/html"
    backup_dir: "/var/backups/website"

    # Gym Tracker app (playbooks/deploy-app.yml)
    app_dir: "/opt/gymapp"
    app_port: 8099
    admin_username: "admin"
```

## Testing

Run tests to make sure everything works:

```bash
# Quick test
./scripts/run-tests.sh quick

# Full test suite
./scripts/run-tests.sh

# Test specific functionality
ansible-playbook playbooks/tests/test-playbooks.yml
```

## Troubleshooting

### Can't Connect to Server
```bash
# Full diagnostics
./scripts/test-connectivity.sh

# Test SSH directly
ssh gym

# Check Ansible inventory
ansible-config view

# Debug connection
ansible gym-server -m ping -vvv
```

### Website Not Loading
```bash
# Check if Apache is running
ansible gym-server -m shell -a "systemctl status httpd"

# Restart Apache
ansible gym-server -m systemd -a "name=httpd state=restarted"

# Check file permissions
ansible gym-server -m shell -a "ls -la /var/www/html/"
```

### Deployment Fails
```bash
# Check if website/index.html exists locally
ls -la website/index.html

# Check server disk space
ansible gym-server -m shell -a "df -h"

# Check error logs
ansible gym-server -m shell -a "tail -20 /var/log/httpd/error_log"
```

## Performance Testing

```bash
# Deploy load-testing tools to the server and run the full suite
./scripts/run-performance-tests.sh

# Run only local load tests against the deployed site
./scripts/local-performance-test.sh

# Monitor resource usage during a test run
./scripts/monitor-resources.sh 300
```

See `docs/PERFORMANCE_BASELINE_REPORT.md` and `docs/SCALING_RECOMMENDATIONS.md` for historical results and scaling guidance.

## Real-World Examples

### Personal Blog Setup
```bash
# 1. Replace website/index.html with your content
vim website/index.html

# 2. Deploy
ansible-playbook playbooks/deploy-local.yml

# 3. Update regularly
ansible-playbook playbooks/deploy-local-quick.yml
```

### Team Website with Git Workflow
```bash
# 1. Set up Git repository
git init
git add website/index.html
git commit -m "Initial website"
git remote add origin https://github.com/team/website.git
git push -u origin main

# 2. Configure deployment
# Edit inventory.yml with your repo URL

# 3. Deploy
ansible-playbook playbooks/deploy-website.yml

# 4. Team workflow
# Team members push to Git, then anyone can deploy:
ansible-playbook playbooks/deploy-website.yml
```

### Backup Before Major Changes
```bash
# Before big updates
ansible-playbook playbooks/backup.yml

# Make your changes
vim website/index.html

# Deploy
ansible-playbook playbooks/deploy-local.yml

# If something breaks, restore:
ansible-playbook playbooks/rollback.yml
```

## Tips for Success

1. **Start Simple**: Deploy a basic HTML file first, then add complexity
2. **Test Changes**: Always test in a browser after deployment
3. **Use Backups**: Create backups before major changes
4. **Monitor Logs**: Check logs if something doesn't work
5. **Keep It Updated**: Regularly update your content

## System Requirements

- **Control Machine**: Any computer with Ansible and SSH
- **Target Server**: Linux server with Apache installed
- **SSH Access**: Key-based authentication to the server
- **Disk Space**: Minimal (website files + backups)

## Security Notes

- Uses SSH key authentication (no passwords)
- Creates backups before destructive operations
- Sets proper file permissions (apache:apache for static files, gymapp:gymapp for the app)
- Runs in isolated container environment
- The Gym Tracker app runs as its own unprivileged `gymapp` system user (not `apache`, not `root`)
- Admin password is hashed (never stored in plaintext) and only ever printed to your terminal once, on first deploy - it is never committed to git or written into any file in this repo

## Support

- **Test your setup**: Run `./scripts/run-tests.sh`
- **Check logs**: Look in `/var/log/httpd/` on the server
- **Documentation**: Visit http://192.168.1.11/readme.html
- **Emergency**: Use `ansible-playbook playbooks/rollback.yml`

## License

This is a personal project template. Use it however you like.

---

**Quick Reference**:
- Deploy: `ansible-playbook playbooks/deploy-local.yml`
- Test: `./scripts/run-tests.sh quick`
- Backup: `ansible-playbook playbooks/backup.yml`
- Rollback: `ansible-playbook playbooks/rollback.yml`
- Website: http://192.168.1.11
