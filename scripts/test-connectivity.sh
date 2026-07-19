#!/bin/bash

# Connectivity Test Script for Gym Website Deployment
# Tests all aspects of connectivity before deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

TARGET_HOST="192.168.1.11"

echo -e "${BLUE}🔍 Gym Website Deployment - Connectivity Test${NC}"
echo "================================================"

# Test 1: Basic network connectivity
echo -e "${YELLOW}1. Testing network connectivity...${NC}"
if ping -c 1 -W 5 "$TARGET_HOST" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Host $TARGET_HOST is reachable${NC}"
else
    echo -e "${RED}✗ Host $TARGET_HOST is not reachable${NC}"
    echo "  Please check:"
    echo "  - Is the target host running?"
    echo "  - Are there network connectivity issues?"
    echo "  - Is the IP address correct?"
    exit 1
fi

# Test 2: SSH port availability
echo -e "${YELLOW}2. Testing SSH port 22...${NC}"
if timeout 10 bash -c "cat < /dev/null > /dev/tcp/$TARGET_HOST/22" 2>/dev/null; then
    echo -e "${GREEN}✓ SSH port 22 is open${NC}"
else
    echo -e "${RED}✗ SSH port 22 is not accessible${NC}"
    echo "  Please check:"
    echo "  - Is SSH server running on the target?"
    echo "  - Is firewall blocking port 22?"
    exit 1
fi

# Test 3: SSH authentication
echo -e "${YELLOW}3. Testing SSH authentication...${NC}"
if ssh -o ConnectTimeout=10 -o BatchMode=yes root@$TARGET_HOST "exit" 2>/dev/null; then
    echo -e "${GREEN}✓ SSH authentication successful${NC}"
else
    echo -e "${RED}✗ SSH authentication failed${NC}"
    echo "  Please check:"
    echo "  - Are SSH keys properly configured?"
    echo "  - Try: ssh-copy-id root@$TARGET_HOST"
    echo "  - Or test manually: ssh root@$TARGET_HOST"
    exit 1
fi

# Test 4: Ansible connectivity
echo -e "${YELLOW}4. Testing Ansible connectivity...${NC}"
if ansible gym-server -m ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Ansible can connect to gym-server${NC}"
else
    echo -e "${RED}✗ Ansible cannot connect to gym-server${NC}"
    echo "  Trying verbose mode..."
    ansible gym-server -m ping -vvv
    exit 1
fi

# Test 5: Check if Apache is available
echo -e "${YELLOW}5. Testing Apache availability...${NC}"
APACHE_CHECK=$(ansible gym-server -m shell -a "which httpd || which apache2" 2>/dev/null | grep -v "CHANGED\|SUCCESS" || echo "not-found")
if [[ "$APACHE_CHECK" != "not-found" && "$APACHE_CHECK" != "" ]]; then
    echo -e "${GREEN}✓ Apache/httpd found on target system${NC}"
else
    echo -e "${YELLOW}⚠ Apache/httpd not found - may need installation${NC}"
    echo "  Apache installation may be required on target"
fi

# Test 6: Check Apache service status
echo -e "${YELLOW}6. Testing Apache service status...${NC}"
APACHE_STATUS=$(ansible gym-server -m shell -a "systemctl is-active httpd 2>/dev/null || systemctl is-active apache2 2>/dev/null" 2>/dev/null | grep -v "CHANGED\|SUCCESS" || echo "inactive")
if [[ "$APACHE_STATUS" == "active" ]]; then
    echo -e "${GREEN}✓ Apache service is running${NC}"
else
    echo -e "${YELLOW}⚠ Apache service is not active${NC}"
    echo "  Apache service may need to be started"
fi

# Test 7: Test HTTP port 80
echo -e "${YELLOW}7. Testing HTTP port 80...${NC}"
if timeout 10 bash -c "cat < /dev/null > /dev/tcp/$TARGET_HOST/80" 2>/dev/null; then
    echo -e "${GREEN}✓ HTTP port 80 is accessible${NC}"
else
    echo -e "${YELLOW}⚠ HTTP port 80 is not accessible${NC}"
    echo "  Apache may need to be started or configured"
fi

# Test 8: Check web directory structure
echo -e "${YELLOW}8. Testing web directory structure...${NC}"
WEB_DIR_CHECK=$(ansible gym-server -m stat -a "path=/var/www/html" 2>/dev/null | grep "exists.*true" || echo "not-found")
if [[ "$WEB_DIR_CHECK" != "not-found" ]]; then
    echo -e "${GREEN}✓ Web directory /var/www/html exists${NC}"
else
    echo -e "${YELLOW}⚠ Web directory /var/www/html may need creation${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Connectivity Test Completed!${NC}"
echo ""
echo -e "${BLUE}Summary:${NC}"
echo "- Target Host: $TARGET_HOST"
echo "- Network: Reachable"
echo "- SSH: Accessible and authenticated"
echo "- Ansible: Connected"
echo "- Ready for deployment!"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Deploy website: ./scripts/manage.sh local"
echo "2. Or run full deployment: ./scripts/manage.sh deploy"
echo "3. Check deployment: ./scripts/manage.sh status"
echo "4. View website: http://$TARGET_HOST/"
echo ""