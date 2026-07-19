#!/bin/bash

# Local Performance Testing Script for Gym Website
# This script runs performance tests from your local machine against the deployed website

set -e

# Configuration
TARGET_HOST="192.168.1.11"
WEBSITE_URL="http://$TARGET_HOST"
LOCAL_RESULTS_DIR="./performance_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$LOCAL_RESULTS_DIR/test_$TIMESTAMP"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Create results directory
mkdir -p "$RESULTS_DIR"

log "Starting performance testing for Gym Website"
log "Target: $WEBSITE_URL"
log "Results directory: $RESULTS_DIR"

# Check dependencies
check_dependencies() {
    local deps=("curl" "ab" "siege")
    local missing=()

    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            missing+=("$dep")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        error "Missing dependencies: ${missing[*]}"
        log "Please install missing tools:"
        echo "  - macOS: brew install httpie siege"
        echo "  - Ubuntu: apt-get install apache2-utils siege"
        echo "  - RHEL/Fedora: dnf install httpd-tools siege"
        exit 1
    fi
}

# Test connectivity
test_connectivity() {
    log "Testing connectivity to $TARGET_HOST..."

    # Ping test
    if ping -c 3 "$TARGET_HOST" &> /dev/null; then
        success "Host $TARGET_HOST is reachable"
    else
        error "Host $TARGET_HOST is not reachable"
        exit 1
    fi

    # HTTP test
    if curl -s --connect-timeout 5 "$WEBSITE_URL" > /dev/null; then
        success "Website is accessible at $WEBSITE_URL"
    else
        error "Website is not accessible at $WEBSITE_URL"
        exit 1
    fi
}

# Basic response test
test_basic_response() {
    log "Testing basic website response..."

    local response_file="$RESULTS_DIR/basic_response.txt"

    {
        echo "=== Basic Response Test ==="
        echo "Timestamp: $(date)"
        echo "URL: $WEBSITE_URL"
        echo ""

        # Response time test
        echo "Response Time Test:"
        for i in {1..5}; do
            response_time=$(curl -o /dev/null -s -w "%{time_total}\n" "$WEBSITE_URL")
            echo "Request $i: ${response_time}s"
        done
        echo ""

        # HTTP headers
        echo "HTTP Headers:"
        curl -I "$WEBSITE_URL"
        echo ""

        # Response size
        echo "Response Size:"
        curl -s "$WEBSITE_URL" | wc -c
        echo ""

    } > "$response_file"

    success "Basic response test completed"
}

# Load testing with Apache Bench
test_load_ab() {
    log "Running Apache Bench load tests..."

    local concurrent_users=(1 5 10 25 50)
    local requests_per_test=100

    for users in "${concurrent_users[@]}"; do
        log "Testing with $users concurrent users ($requests_per_test requests each)..."

        local output_file="$RESULTS_DIR/ab_${users}users.txt"

        ab -n $((users * requests_per_test)) -c "$users" "$WEBSITE_URL/" > "$output_file" 2>&1

        # Extract key metrics
        local success_rate=$(grep "Complete requests:" "$output_file" | awk '{print $3}')
        local failed_rate=$(grep "Failed requests:" "$output_file" | awk '{print $3}')
        local time_per_request=$(grep "Time per request:" "$output_file" | head -1 | awk '{print $4}')
        local requests_per_sec=$(grep "Requests per second:" "$output_file" | awk '{print $4}')

        log "  Results: $success_rate success, $failed_rate failed, ${time_per_request}ms avg, ${requests_per_sec} req/s"
    done

    success "Apache Bench tests completed"
}

# Load testing with Siege
test_load_siege() {
    log "Running Siege load tests..."

    local concurrent_users=(1 5 10 25 50)
    local duration="30s"

    for users in "${concurrent_users[@]}"; do
        log "Testing with $users concurrent users for $duration..."

        local output_file="$RESULTS_DIR/siege_${users}users.txt"

        siege -c "$users" -t "$duration" "$WEBSITE_URL/" > "$output_file" 2>&1

        # Extract key metrics
        local transactions=$(grep "Transactions:" "$output_file" | awk '{print $2}')
        local response_time=$(grep "Response time:" "$output_file" | awk '{print $3}')
        local throughput=$(grep "Throughput:" "$output_file" | awk '{print $2}')

        log "  Results: $transactions transactions, ${response_time}s avg response, ${throughput} MB/s"
    done

    success "Siege tests completed"
}

# Stress test with increasing load
test_stress() {
    log "Running stress test with increasing load..."

    local stress_file="$RESULTS_DIR/stress_test.txt"

    {
        echo "=== Stress Test Results ==="
        echo "Timestamp: $(date)"
        echo ""

        for users in 1 10 25 50 100; do
            echo "Testing $users concurrent users..."

            # Run short ab test to get baseline
            ab -n $((users * 10)) -c "$users" "$WEBSITE_URL/" 2>&1 | \
                grep -E "(Requests per second|Time per request|Transfer rate)"

            echo ""
            sleep 2
        done

    } > "$stress_file"

    success "Stress test completed"
}

# Test different content types
test_content_types() {
    log "Testing different content types..."

    local content_file="$RESULTS_DIR/content_types.txt"

    {
        echo "=== Content Type Tests ==="
        echo "Timestamp: $(date)"
        echo ""

        # Test main page
        echo "Main page (HTML):"
        curl -s -w "Size: %{size_download} bytes, Time: %{time_total}s\n" \
             -o /dev/null "$WEBSITE_URL/"

        # Test CSS files if they exist
        echo "CSS files:"
        curl -s -w "Size: %{size_download} bytes, Time: %{time_total}s\n" \
             -o /dev/null "$WEBSITE_URL/style.css" 2>/dev/null || echo "No CSS file found"

        # Test images if they exist
        echo "Images:"
        curl -s -w "Size: %{size_download} bytes, Time: %{time_total}s\n" \
             -o /dev/null "$WEBSITE_URL/favicon.ico" 2>/dev/null || echo "No favicon found"

    } > "$content_file"

    success "Content type tests completed"
}

# Network latency and throughput test
test_network() {
    log "Testing network performance..."

    local network_file="$RESULTS_DIR/network_test.txt"

    {
        echo "=== Network Performance Test ==="
        echo "Timestamp: $(date)"
        echo ""

        echo "Network Latency (ping):"
        ping -c 10 "$TARGET_HOST" | grep -E "(min/avg/max|packet loss)"
        echo ""

        echo "HTTP Connection Times:"
        for i in {1..5}; do
            curl -w "Connect: %{time_connect}s, SSL: %{time_appconnect}s, Total: %{time_total}s\n" \
                 -o /dev/null -s "$WEBSITE_URL"
        done
        echo ""

        echo "Download Speed Test:"
        # Test download speed with website content
        curl -w "Downloaded %{size_download} bytes in %{time_total}s (avg: %{speed_download} bytes/s)\n" \
             -o /dev/null -s "$WEBSITE_URL/"

    } > "$network_file"

    success "Network tests completed"
}

# Generate performance report
generate_report() {
    log "Generating performance report..."

    local report_file="$RESULTS_DIR/performance_report.md"

    {
        echo "# Gym Website Performance Report"
        echo ""
        echo "**Generated:** $(date)"
        echo "**Target:** $WEBSITE_URL"
        echo "**Test Duration:** $(date -r $(dirname "$RESULTS_DIR" | xargs stat -f %B) '+%H:%M:%S')"
        echo ""

        echo "## Test Summary"
        echo ""

        # Extract key metrics from AB tests
        if [ -f "$RESULTS_DIR/ab_50users.txt" ]; then
            echo "### Load Test Results (50 concurrent users)"
            echo ""
            grep -E "(Complete requests|Failed requests|Requests per second|Time per request)" \
                "$RESULTS_DIR/ab_50users.txt" | sed 's/^/- /'
            echo ""
        fi

        # Extract key metrics from Siege tests
        if [ -f "$RESULTS_DIR/siege_50users.txt" ]; then
            echo "### Siege Test Results (50 concurrent users)"
            echo ""
            grep -E "(Transactions|Response time|Throughput)" \
                "$RESULTS_DIR/siege_50users.txt" | sed 's/^/- /'
            echo ""
        fi

        echo "## Performance Recommendations"
        echo ""
        echo "### Scaling Recommendations"
        echo "- **Low Load (1-10 users):** Current setup should handle well"
        echo "- **Medium Load (10-25 users):** Monitor response times"
        echo "- **High Load (25+ users):** Consider optimizations:"
        echo "  - Enable Apache mod_deflate for compression"
        echo "  - Implement caching headers"
        echo "  - Optimize images and CSS"
        echo "  - Consider CDN for static assets"
        echo ""

        echo "### Resource Monitoring"
        echo "- Set up regular performance monitoring"
        echo "- Monitor server resources during peak times"
        echo "- Implement automated alerts for response time degradation"
        echo ""

        echo "## Test Files"
        echo ""
        ls -la "$RESULTS_DIR"/*.txt | awk '{print "- " $9}' | sed "s|$RESULTS_DIR/|- |"
        echo ""

        echo "## Next Steps"
        echo "1. Review individual test files for detailed metrics"
        echo "2. Set up continuous monitoring"
        echo "3. Implement performance optimizations based on findings"
        echo "4. Establish performance baselines for comparison"

    } > "$report_file"

    success "Performance report generated: $report_file"
}

# Main execution
main() {
    log "=== GYM WEBSITE PERFORMANCE TESTING SUITE ==="

    # Check dependencies
    check_dependencies

    # Test connectivity
    test_connectivity

    # Run performance tests
    test_basic_response
    test_load_ab
    test_load_siege
    test_stress
    test_content_types
    test_network

    # Generate report
    generate_report

    echo ""
    success "Performance testing completed successfully!"
    log "Results saved to: $RESULTS_DIR"
    log "Performance report: $RESULTS_DIR/performance_report.md"
    echo ""

    # Display quick summary
    if [ -f "$RESULTS_DIR/ab_50users.txt" ]; then
        echo "Quick Summary:"
        echo "=============="
        grep "Requests per second" "$RESULTS_DIR/ab_50users.txt" | head -1
        grep "Time per request" "$RESULTS_DIR/ab_50users.txt" | head -1
    fi
}

# Handle script arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [options]"
        echo ""
        echo "Options:"
        echo "  -h, --help    Show this help message"
        echo ""
        echo "This script runs comprehensive performance tests against the gym website."
        echo "Results are saved to $LOCAL_RESULTS_DIR/test_TIMESTAMP/"
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac