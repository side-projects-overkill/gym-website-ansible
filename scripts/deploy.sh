#!/bin/bash

# Gym Website Deployment Script
# Usage: ./deploy.sh [quick|backup|deploy] [git-repo-url]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Default values
ACTION="${1:-deploy}"
GIT_REPO="${2:-https://github.com/your-username/gym-website.git}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo -e "${BLUE}Gym Website Deployment Tool${NC}"
    echo ""
    echo "Usage: $0 [ACTION] [GIT_REPO_URL]"
    echo ""
    echo "Actions:"
    echo "  deploy    - Full deployment with backup (default)"
    echo "  quick     - Quick deployment without backup"
    echo "  backup    - Backup current website only"
    echo "  test      - Test connection to server"
    echo ""
    echo "Examples:"
    echo "  $0 deploy https://github.com/user/gym-website.git"
    echo "  $0 quick"
    echo "  $0 backup"
    echo ""
}

test_connection() {
    echo -e "${BLUE}Testing connection to gym server...${NC}"
    if ansible gym-server -m ping; then
        echo -e "${GREEN}✓ Connection successful${NC}"
        return 0
    else
        echo -e "${RED}✗ Connection failed${NC}"
        return 1
    fi
}

update_git_repo() {
    local repo_url="$1"
    echo -e "${YELLOW}Updating Git repository URL to: $repo_url${NC}"
    sed -i.bak "s|git_repo_url:.*|git_repo_url: \"$repo_url\"|" inventory.yml
}

case "$ACTION" in
    "deploy")
        echo -e "${GREEN}🚀 Starting full website deployment...${NC}"
        update_git_repo "$GIT_REPO"
        test_connection
        ansible-playbook playbooks/deploy-website.yml
        echo -e "${GREEN}✓ Deployment completed!${NC}"
        ;;
    "quick")
        echo -e "${YELLOW}⚡ Starting quick deployment...${NC}"
        update_git_repo "$GIT_REPO"
        test_connection
        ansible-playbook playbooks/deploy-quick.yml
        echo -e "${GREEN}✓ Quick deployment completed!${NC}"
        ;;
    "backup")
        echo -e "${BLUE}💾 Creating backup of current website...${NC}"
        test_connection
        ansible-playbook playbooks/backup.yml
        echo -e "${GREEN}✓ Backup completed!${NC}"
        ;;
    "test")
        test_connection
        ;;
    "help"|"-h"|"--help")
        print_usage
        ;;
    *)
        echo -e "${RED}Error: Unknown action '$ACTION'${NC}"
        print_usage
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}Website URL: http://192.168.1.11/${NC}"