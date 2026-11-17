#!/bin/bash

# Gym Website Management Script
# Comprehensive management tool for the gym website

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_usage() {
    echo -e "${PURPLE}🏋️  Gym Website Management Tool${NC}"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo -e "${BLUE}Deployment Commands:${NC}"
    echo "  app [password]      - Deploy the Gym Tracker app (primary target)"
    echo "  deploy [repo-url]   - Full deployment with backup"
    echo "  quick [repo-url]    - Quick deployment without backup"
    echo "  local              - Deploy local index.html with backup"
    echo "  local-quick        - Deploy local index.html without backup"
    echo "  backup             - Backup current website only"
    echo ""
    echo -e "${BLUE}Tip: the Makefile is the easiest entrypoint - 'make help'${NC}"
    echo ""
    echo -e "${BLUE}Management Commands:${NC}"
    echo "  status             - Check server and website status"
    echo "  logs               - View Apache access/error logs"
    echo "  rollback           - Rollback to previous backup"
    echo "  list-backups       - List available backups"
    echo "  test               - Test connection and website"
    echo "  shell              - Open SSH shell to server"
    echo ""
    echo -e "${BLUE}Maintenance Commands:${NC}"
    echo "  restart-apache     - Restart Apache web server"
    echo "  clean-backups      - Remove old backups (keep last 5)"
    echo "  disk-usage         - Show server disk usage"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 deploy https://github.com/user/gym-website.git"
    echo "  $0 quick"
    echo "  $0 local              # Deploy index.html from current folder"
    echo "  $0 local-quick        # Quick local deploy"
    echo "  $0 status"
    echo "  $0 rollback"
    echo ""
}

run_ansible_command() {
    local command="$1"
    echo -e "${BLUE}Running: $command${NC}"
    ansible gym-server -m shell -a "$command"
}

case "${1:-help}" in
    "app")
        echo -e "${GREEN}🚀 Deploying the Gym Tracker app...${NC}"
        EXTRA_ARGS=""
        if [ -n "$2" ]; then
            EXTRA_ARGS="-e admin_password=$2"
        fi
        ansible-playbook playbooks/deploy-app.yml $EXTRA_ARGS
        ;;
    "app-status")
        echo -e "${BLUE}📊 Gym Tracker app status:${NC}"
        ansible gym-server -m shell -a \
            "uptime; echo; systemctl is-active gymapp httpd; echo; df -h / | tail -1"
        ;;
    "app-logs")
        echo -e "${BLUE}📋 Gym Tracker app logs (last 50 lines):${NC}"
        ansible gym-server -m shell -a "journalctl -u gymapp -n 50 --no-pager"
        ;;
    "app-restart")
        echo -e "${YELLOW}🔄 Restarting gymapp service...${NC}"
        ansible gym-server -m systemd -a "name=gymapp state=restarted"
        ;;
    "deploy")
        echo -e "${GREEN}🚀 Starting full website deployment...${NC}"
        if [ -n "$2" ]; then
            sed -i.bak "s|git_repo_url:.*|git_repo_url: \"$2\"|" inventory.yml
        fi
        ansible-playbook playbooks/deploy-website.yml
        ;;
    "quick")
        echo -e "${YELLOW}⚡ Starting quick deployment...${NC}"
        if [ -n "$2" ]; then
            sed -i.bak "s|git_repo_url:.*|git_repo_url: \"$2\"|" inventory.yml
        fi
        ansible-playbook playbooks/deploy-quick.yml
        ;;
    "local")
        echo -e "${GREEN}📄 Deploying local website/index.html with backup...${NC}"
        if [ ! -f "website/index.html" ]; then
            echo -e "${RED}Error: website/index.html not found${NC}"
            exit 1
        fi
        ansible-playbook playbooks/deploy-local.yml
        ;;
    "local-quick")
        echo -e "${YELLOW}⚡ Quick local deployment...${NC}"
        if [ ! -f "website/index.html" ]; then
            echo -e "${RED}Error: website/index.html not found${NC}"
            exit 1
        fi
        ansible-playbook playbooks/deploy-local.yml -e "backup_local=false"
        ;;
    "backup")
        echo -e "${BLUE}💾 Creating backup...${NC}"
        ansible-playbook playbooks/backup.yml
        ;;
    "status")
        echo -e "${BLUE}📊 Server Status:${NC}"
        run_ansible_command "uptime && systemctl status httpd --no-pager && df -h /"
        ;;
    "logs")
        echo -e "${BLUE}📋 Apache Logs:${NC}"
        echo -e "${YELLOW}=== Error Log (last 10 lines) ===${NC}"
        run_ansible_command "tail -10 /var/log/httpd/error_log || echo 'No error log found'"
        echo -e "${YELLOW}=== Access Log (last 10 lines) ===${NC}"
        run_ansible_command "tail -10 /var/log/httpd/access_log || echo 'No access log found'"
        ;;
    "rollback")
        echo -e "${RED}🔄 Initiating rollback...${NC}"
        ansible-playbook playbooks/rollback.yml
        ;;
    "list-backups")
        echo -e "${BLUE}📦 Available Backups:${NC}"
        run_ansible_command "ls -lah /var/backups/website/*.tar.gz 2>/dev/null || echo 'No backups found'"
        ;;
    "test")
        echo -e "${BLUE}🔍 Testing connection and website...${NC}"
        echo -e "${YELLOW}1. Testing Ansible connection...${NC}"
        ansible gym-server -m ping
        echo -e "${YELLOW}2. Testing website accessibility...${NC}"
        if curl -s -o /dev/null -w "%{http_code}" http://192.168.1.11/ | grep -q "200"; then
            echo -e "${GREEN}✓ Website is accessible${NC}"
        else
            echo -e "${RED}✗ Website is not accessible${NC}"
        fi
        ;;
    "shell")
        echo -e "${BLUE}🔧 Opening SSH shell to gym server...${NC}"
        ssh root@192.168.1.11
        ;;
    "restart-apache")
        echo -e "${YELLOW}🔄 Restarting Apache...${NC}"
        run_ansible_command "systemctl restart httpd && systemctl status httpd --no-pager"
        ;;
    "clean-backups")
        echo -e "${BLUE}🧹 Cleaning old backups...${NC}"
        run_ansible_command "cd /var/backups/website && ls -1t *.tar.gz | tail -n +6 | xargs rm -f && echo 'Cleanup completed'"
        ;;
    "disk-usage")
        echo -e "${BLUE}💽 Disk Usage:${NC}"
        run_ansible_command "df -h && echo && du -sh /var/www/html && echo && du -sh /var/backups/website 2>/dev/null || echo 'No backups directory'"
        ;;
    "help"|"-h"|"--help")
        print_usage
        ;;
    *)
        echo -e "${RED}Error: Unknown command '$1'${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac

echo ""
echo -e "${PURPLE}🌐 Website URL: http://192.168.1.11/${NC}"