#!/bin/bash

# Performance Testing Runner for Gym Website
# This script orchestrates both local and remote performance tests

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_HOST="192.168.1.11"
WEBSITE_URL="http://$TARGET_HOST"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$SCRIPT_DIR/performance_results_$TIMESTAMP"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if we can reach the target
check_connectivity() {
    log "Checking connectivity to $TARGET_HOST..."

    if ! ping -c 1 "$TARGET_HOST" &> /dev/null; then
        error "Cannot reach $TARGET_HOST"
        return 1
    fi

    if ! ansible gym-server -m ping &> /dev/null; then
        error "Ansible cannot connect to gym-server"
        log "Please ensure SSH connectivity is established"
        return 1
    fi

    success "Connectivity confirmed"
    return 0
}

# Deploy performance testing tools
deploy_performance_tools() {
    log "Deploying performance testing tools to target server..."

    if ansible-playbook playbooks/performance-test.yml; then
        success "Performance tools deployed successfully"
    else
        error "Failed to deploy performance tools"
        return 1
    fi
}

# Run remote performance tests
run_remote_tests() {
    log "Running performance tests on target server..."

    # Run the comprehensive performance test suite
    ansible gym-server -m shell -a "/usr/local/bin/run_all_performance_tests.sh $WEBSITE_URL" \
        --become

    # Fetch results from remote server
    mkdir -p "$RESULTS_DIR/remote"

    log "Fetching remote test results..."

    # Get performance test results
    ansible gym-server -m fetch \
        -a "src=/tmp/performance_tests/ dest=$RESULTS_DIR/remote/ flat=no" \
        || warning "Could not fetch all remote test results"

    # Get performance report
    REPORT_FILE=$(ansible gym-server -m shell -a "ls /tmp/performance_baseline_*.txt | tail -1" | grep -v ">>>" | tail -1)
    if [ -n "$REPORT_FILE" ]; then
        ansible gym-server -m fetch \
            -a "src=$REPORT_FILE dest=$RESULTS_DIR/remote/ flat=yes"
        success "Remote performance report fetched"
    fi
}

# Run local performance tests
run_local_tests() {
    log "Running local performance tests..."

    if [ -f "$SCRIPT_DIR/local-performance-test.sh" ]; then
        (cd "$SCRIPT_DIR" && ./local-performance-test.sh)

        # Move local results to our results directory
        if [ -d "$SCRIPT_DIR/performance_results" ]; then
            mv "$SCRIPT_DIR/performance_results" "$RESULTS_DIR/local"
            success "Local test results moved to $RESULTS_DIR/local"
        fi
    else
        warning "Local performance test script not found"
    fi
}

# Monitor resource usage during tests
monitor_resources() {
    log "Starting resource monitoring..."

    # Start monitoring on remote server
    ansible gym-server -m shell \
        -a "nohup top -b -d 1 -n 300 > /tmp/resource_monitor.log 2>&1 &" \
        --become

    # Monitor local network usage
    if command -v iftop &> /dev/null; then
        log "Starting local network monitoring..."
        timeout 300 iftop -t -s 1 > "$RESULTS_DIR/local_network_monitor.log" 2>&1 &
    fi
}

# Stop resource monitoring
stop_monitoring() {
    log "Stopping resource monitoring..."

    # Stop monitoring on remote server
    ansible gym-server -m shell \
        -a "pkill -f 'top -b -d 1'" \
        --become || true

    # Fetch monitoring results
    ansible gym-server -m fetch \
        -a "src=/tmp/resource_monitor.log dest=$RESULTS_DIR/remote/ flat=yes" \
        || warning "Could not fetch resource monitoring log"

    # Stop local monitoring
    pkill -f iftop || true
}

# Generate comprehensive report
generate_comprehensive_report() {
    log "Generating comprehensive performance report..."

    local report_file="$RESULTS_DIR/comprehensive_performance_report.md"

    {
        echo "# Comprehensive Gym Website Performance Report"
        echo ""
        echo "**Generated:** $(date)"
        echo "**Target:** $WEBSITE_URL"
        echo "**Test Suite:** Local + Remote Performance Testing"
        echo ""

        echo "## Executive Summary"
        echo ""

        # System Information
        if [ -f "$RESULTS_DIR/remote/performance_baseline_"*".txt" ]; then
            echo "### System Configuration"
            echo "\`\`\`"
            grep -A 10 "=== SYSTEM SPECIFICATIONS ===" "$RESULTS_DIR/remote/performance_baseline_"*".txt" | head -15
            echo "\`\`\`"
            echo ""
        fi

        # Performance Metrics
        echo "### Key Performance Metrics"
        echo ""

        # Local test results
        if [ -f "$RESULTS_DIR/local/"*"/ab_50users.txt" ]; then
            echo "#### Load Test Results (50 concurrent users from external client)"
            grep -E "(Complete requests|Failed requests|Requests per second|Time per request)" \
                "$RESULTS_DIR/local/"*"/ab_50users.txt" | sed 's/^/- /'
            echo ""
        fi

        # Remote test results
        if [ -f "$RESULTS_DIR/remote/"*"/load_test_"*"/ab_50users.txt" ]; then
            echo "#### Load Test Results (50 concurrent users from server localhost)"
            grep -E "(Complete requests|Failed requests|Requests per second|Time per request)" \
                "$RESULTS_DIR/remote/"*"/load_test_"*"/ab_50users.txt" | head -4 | sed 's/^/- /'
            echo ""
        fi

        echo "## Detailed Analysis"
        echo ""

        echo "### Scaling Analysis"
        echo ""
        echo "| Concurrent Users | Requests/sec | Avg Response Time | Status |"
        echo "|------------------|--------------|-------------------|--------|"

        for users in 1 5 10 25 50; do
            if [ -f "$RESULTS_DIR/local/"*"/ab_${users}users.txt" ]; then
                local rps=$(grep "Requests per second:" "$RESULTS_DIR/local/"*"/ab_${users}users.txt" | awk '{print $4}')
                local rt=$(grep "Time per request:" "$RESULTS_DIR/local/"*"/ab_${users}users.txt" | head -1 | awk '{print $4}')
                local status="✅ Good"

                # Simple performance assessment
                if (( $(echo "$rt > 1000" | bc -l) )); then
                    status="⚠️ Slow"
                fi
                if (( $(echo "$rt > 5000" | bc -l) )); then
                    status="❌ Poor"
                fi

                echo "| $users | $rps | ${rt}ms | $status |"
            fi
        done

        echo ""

        echo "### Resource Utilization"
        echo ""
        if [ -f "$RESULTS_DIR/remote/resource_monitor.log" ]; then
            echo "**Peak Resource Usage during tests:**"
            echo "\`\`\`"
            # Extract peak CPU and memory usage
            tail -50 "$RESULTS_DIR/remote/resource_monitor.log" | head -10
            echo "\`\`\`"
            echo ""
        fi

        echo "## Performance Recommendations"
        echo ""

        echo "### Immediate Actions"
        echo "- [ ] Review response times under different load levels"
        echo "- [ ] Set up continuous monitoring"
        echo "- [ ] Establish performance baselines"
        echo ""

        echo "### Scaling Recommendations"
        echo ""

        # Generate recommendations based on test results
        if [ -f "$RESULTS_DIR/local/"*"/ab_50users.txt" ]; then
            local failed_requests=$(grep "Failed requests:" "$RESULTS_DIR/local/"*"/ab_50users.txt" | awk '{print $3}')
            local avg_response=$(grep "Time per request:" "$RESULTS_DIR/local/"*"/ab_50users.txt" | head -1 | awk '{print $4}')

            if [ "$failed_requests" -gt 0 ]; then
                echo "⚠️ **High Priority:** Failed requests detected under load"
                echo "- Investigate Apache configuration"
                echo "- Check resource limits"
                echo "- Review error logs"
                echo ""
            fi

            if (( $(echo "$avg_response > 1000" | bc -l) )); then
                echo "⚠️ **Medium Priority:** Response times > 1 second under load"
                echo "- Enable compression (mod_deflate)"
                echo "- Optimize static content delivery"
                echo "- Consider caching strategies"
                echo ""
            fi
        fi

        echo "### Monitoring Setup"
        echo "- Set up automated performance monitoring"
        echo "- Configure alerts for response time degradation"
        echo "- Implement resource usage monitoring"
        echo "- Schedule regular load testing"
        echo ""

        echo "## Test Artifacts"
        echo ""
        echo "### Local Test Results"
        if [ -d "$RESULTS_DIR/local" ]; then
            find "$RESULTS_DIR/local" -name "*.txt" -o -name "*.md" | sed "s|$RESULTS_DIR/local/|- |"
        fi
        echo ""

        echo "### Remote Test Results"
        if [ -d "$RESULTS_DIR/remote" ]; then
            find "$RESULTS_DIR/remote" -name "*.txt" -o -name "*.log" | sed "s|$RESULTS_DIR/remote/|- |"
        fi

    } > "$report_file"

    success "Comprehensive report generated: $report_file"
}

# Main execution
main() {
    local run_mode="${1:-full}"

    echo ""
    log "=== GYM WEBSITE PERFORMANCE & SCALABILITY TESTING ==="
    log "Mode: $run_mode"
    log "Target: $WEBSITE_URL"
    log "Results: $RESULTS_DIR"
    echo ""

    cd "$PROJECT_ROOT"
    mkdir -p "$RESULTS_DIR"

    case "$run_mode" in
        "connectivity")
            check_connectivity
            ;;
        "local")
            if check_connectivity; then
                run_local_tests
                generate_comprehensive_report
            fi
            ;;
        "remote")
            if check_connectivity; then
                deploy_performance_tools
                run_remote_tests
                generate_comprehensive_report
            fi
            ;;
        "full"|*)
            if check_connectivity; then
                # Deploy tools
                deploy_performance_tools

                # Start monitoring
                monitor_resources

                # Run tests
                run_local_tests
                run_remote_tests

                # Stop monitoring
                stop_monitoring

                # Generate report
                generate_comprehensive_report

                echo ""
                success "Complete performance testing finished!"
                log "Results directory: $RESULTS_DIR"
                log "Comprehensive report: $RESULTS_DIR/comprehensive_performance_report.md"
            else
                error "Cannot proceed without connectivity"
                exit 1
            fi
            ;;
    esac
}

# Help function
show_help() {
    echo "Usage: $0 [mode]"
    echo ""
    echo "Modes:"
    echo "  full         Run complete performance testing suite (default)"
    echo "  local        Run only local performance tests"
    echo "  remote       Run only remote performance tests"
    echo "  connectivity Test connectivity only"
    echo ""
    echo "Examples:"
    echo "  $0                # Run full test suite"
    echo "  $0 local         # Run only local tests"
    echo "  $0 connectivity  # Test connectivity"
}

# Handle arguments
case "${1:-}" in
    -h|--help)
        show_help
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac