# Gym Tracker - one-command operations.
#
# The easy way to run everything in this repo:
#   make help        - list all targets
#   make check       - pre-flight: connectivity + full local test suite
#   make deploy      - deploy the Gym Tracker app (primary use case)
#   make backup      - manual backup of website + app data
#
# All targets are thin wrappers around the Ansible playbooks / scripts
# in this repo - nothing here duplicates logic.

.DEFAULT_GOAL := help
.PHONY: help check test deploy deploy-app deploy-website deploy-quick \
        deploy-local backup rollback status logs restart shell \
        health clean-backups ansible-check

ANSIBLE        := ansible-playbook
SERVER         := gym-server

help: ## Show this help
	@echo "Gym Tracker operations (make <target>):"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Extra vars: make deploy EXTRA='-e admin_password=secret'   (first run only)"

# ---- safety / verification -------------------------------------------------

check: test ansible-check ## Full pre-flight: local tests + playbook syntax + server ping
	@$(ANSIBLE) $(SERVER) -m ping

test: ## Run the local Python test suite (90 tests, no server needed)
	@./scripts/run-python-tests.sh

ansible-check: ## Syntax-check all playbooks (no server needed)
	@for p in playbooks/*.yml; do \
		$(ANSIBLE) --syntax-check $$p >/dev/null \
			|| { echo "FAILED: $$p"; exit 1; }; \
	done; echo "All playbooks OK"

# ---- deployment ------------------------------------------------------------

deploy: deploy-app ## Deploy the Gym Tracker app (alias)

deploy-app: ## Deploy the Gym Tracker app (systemd + Apache proxy) - PRIMARY
	$(ANSIBLE) playbooks/deploy-app.yml $(EXTRA)

deploy-website: ## Deploy the static site from the Git repo (legacy)
	$(ANSIBLE) playbooks/deploy-website.yml $(EXTRA)

deploy-quick: ## Quick static deploy from Git, no backup (legacy)
	$(ANSIBLE) playbooks/deploy-quick.yml $(EXTRA)

deploy-local: ## Deploy local website/index.html with backup (legacy)
	$(ANSIBLE) playbooks/deploy-local.yml $(EXTRA)

# ---- backup / recovery -----------------------------------------------------

backup: ## Create a manual backup on the server
	$(ANSIBLE) playbooks/backup.yml $(EXTRA)

rollback: ## Emergency restore from the latest backup
	$(ANSIBLE) playbooks/rollback.yml $(EXTRA)

# ---- operations ------------------------------------------------------------

status: ## Server + app status (uptime, services, disk)
	@ansible $(SERVER) -m shell -a \
		"uptime; echo; systemctl is-active gymapp httpd; echo; df -h / | tail -1"

health: ## Verify the live site responds through Apache
	@ansible $(SERVER) -m shell -a \
		"curl -s -o /dev/null -w 'public: %{http_code}\n' http://127.0.0.1/; \
		 curl -s -o /dev/null -w 'login:  %{http_code}\n' http://127.0.0.1/login"

logs: ## Tail the app service journal (Ctrl-C to stop)
	@ansible $(SERVER) -m shell -a "journalctl -u gymapp -n 50 --no-pager"

restart: ## Restart the gymapp service on the server
	@ansible $(SERVER) -m systemd -a "name=gymapp state=restarted"

shell: ## Open an SSH shell on the gym server
	@ssh root@192.168.1.11

clean-backups: ## Remove old website backups, keep the newest 5
	@ansible $(SERVER) -m shell -a \
		"cd /var/backups/website && ls -1t *.tar.gz | tail -n +6 | xargs -r rm -f && echo done"
