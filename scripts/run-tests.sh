#!/bin/bash

# Gym Website Ansible Test Runner
# Comprehensive test suite for all playbooks and functionality

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_header() {
    echo -e "${PURPLE}"
    echo "==========================================="
    echo "🏋️  GYM WEBSITE ANSIBLE TEST SUITE"
    echo "==========================================="
    echo -e "${NC}"
}

print_section() {
    echo -e "${BLUE}📋 $1${NC}"
    echo "-------------------------------------------"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

run_test() {
    local test_name="$1"
    local test_command="$2"

    echo -e "${BLUE}Running: $test_name${NC}"
    if eval "$test_command" >/dev/null 2>&1; then
        print_success "$test_name - PASSED"
        return 0
    else
        print_error "$test_name - FAILED"
        return 1
    fi
}

main() {
    print_header

    # Test counter
    local total_tests=0
    local passed_tests=0
    local failed_tests=0

    print_section "Pre-flight Checks"

    # Check if we're in the right directory
    if [[ ! -f "inventory.yml" ]]; then
        print_error "inventory.yml not found. Are you in the right directory?"
        exit 1
    fi
    print_success "Found inventory.yml"

    # Check if ansible is installed
    if ! command -v ansible >/dev/null 2>&1; then
        print_error "Ansible not found. Please install ansible first."
        exit 1
    fi
    print_success "Ansible is installed"

    # Check connectivity
    print_info "Testing connectivity to gym server..."
    if ansible gym-server -m ping >/dev/null 2>&1; then
        print_success "Connection to gym server - OK"
    else
        print_error "Cannot connect to gym server"
        exit 1
    fi

    echo ""
    print_section "Individual Playbook Tests"

    # Test 1: Connection and basic functionality
    print_info "Test 1: Basic connectivity and server status"
    ((total_tests++))
    if run_test "Server ping test" "ansible gym-server -m ping"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Test 2: Apache service check
    print_info "Test 2: Apache service status"
    ((total_tests++))
    if run_test "Apache service check" "ansible gym-server -m systemd -a 'name=httpd'"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Test 3: Website accessibility
    print_info "Test 3: Website accessibility"
    ((total_tests++))
    if run_test "Website accessibility test" "ansible gym-server -m uri -a 'url=http://192.168.1.11/ method=GET' -c local"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Test 4: File system permissions
    print_info "Test 4: File system and permissions"
    ((total_tests++))
    if run_test "Web directory access" "ansible gym-server -m shell -a 'ls -la /var/www/html/'"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Test 5: Backup directory creation
    print_info "Test 5: Backup functionality"
    ((total_tests++))
    if run_test "Backup directory test" "ansible-playbook playbooks/backup.yml"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Test 6: Local deployment (if website/index.html exists)
    if [[ -f "website/index.html" ]]; then
        print_info "Test 6: Local deployment"
        ((total_tests++))
        if run_test "Local deployment test" "ansible-playbook playbooks/deploy-local.yml -e 'backup_local=false'"; then
            ((passed_tests++))
        else
            ((failed_tests++))
        fi
    else
        print_warning "Skipping local deployment test - no website/index.html found"
    fi

    echo ""
    print_section "Comprehensive Test Suite"

    # Run the comprehensive test playbook
    print_info "Running comprehensive test playbook..."
    ((total_tests++))
    if ansible-playbook playbooks/tests/test-playbooks.yml; then
        print_success "Comprehensive test suite - PASSED"
        ((passed_tests++))
    else
        print_error "Comprehensive test suite - FAILED"
        ((failed_tests++))
    fi

    echo ""
    print_section "System Validation"

    # Final system checks
    print_info "Final system validation..."

    # Check if original website is still intact
    ((total_tests++))
    if run_test "Original website integrity" "ansible gym-server -m stat -a 'path=/var/www/html/index.html'"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    # Check system resources
    ((total_tests++))
    if run_test "System resources check" "ansible gym-server -m shell -a 'df -h && free -h'"; then
        ((passed_tests++))
    else
        ((failed_tests++))
    fi

    echo ""
    print_section "Test Results Summary"

    echo -e "${BLUE}Total Tests: $total_tests${NC}"
    echo -e "${GREEN}Passed: $passed_tests${NC}"
    echo -e "${RED}Failed: $failed_tests${NC}"

    if [[ $failed_tests -eq 0 ]]; then
        echo ""
        print_success "🎉 ALL TESTS PASSED!"
        echo ""
        print_info "System Status: All playbooks and functionality working correctly"
        print_info "Website: http://192.168.1.11/"
        print_info "Documentation: http://192.168.1.11/readme.html"
        echo ""
        return 0
    else
        echo ""
        print_error "❌ $failed_tests TEST(S) FAILED"
        echo ""
        print_warning "Please check the error output above and fix issues before deployment"
        echo ""
        return 1
    fi
}

# Parse command line arguments
case "${1:-run}" in
    "help"|"-h"|"--help")
        echo "Gym Website Ansible Test Runner"
        echo ""
        echo "Usage: $0 [COMMAND]"
        echo ""
        echo "Commands:"
        echo "  run          - Run all tests (default)"
        echo "  quick        - Run only basic connectivity tests"
        echo "  playbooks    - Test all playbooks"
        echo "  help         - Show this help"
        echo ""
        echo "Examples:"
        echo "  $0           # Run all tests"
        echo "  $0 quick     # Quick test only"
        echo "  $0 playbooks # Test playbooks only"
        ;;
    "quick")
        print_header
        print_section "Quick Tests"

        # Basic connectivity only
        if ansible gym-server -m ping >/dev/null 2>&1; then
            print_success "Connection test - PASSED"
        else
            print_error "Connection test - FAILED"
            exit 1
        fi

        if ansible gym-server -m uri -a "url=http://192.168.1.11/ method=GET" -c local >/dev/null 2>&1; then
            print_success "Website test - PASSED"
        else
            print_error "Website test - FAILED"
            exit 1
        fi

        print_success "🎉 Quick tests completed successfully!"
        ;;
    "playbooks")
        print_header
        print_section "Playbook Tests Only"

        # Test each playbook
        if ansible-playbook playbooks/tests/test-playbooks.yml; then
            print_success "🎉 All playbooks working correctly!"
        else
            print_error "❌ Playbook tests failed"
            exit 1
        fi
        ;;
    "run"|*)
        main
        ;;
esac