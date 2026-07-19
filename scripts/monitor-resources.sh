#!/bin/bash

# Real-time Resource Monitoring Script
# Monitors system resources during performance testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MONITOR_DURATION="${1:-300}"  # Default 5 minutes
OUTPUT_DIR="${2:-./monitoring_output}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Create output directory
mkdir -p "$OUTPUT_DIR"

log "Starting resource monitoring for $MONITOR_DURATION seconds"
log "Output directory: $OUTPUT_DIR"

# Function to monitor local system
monitor_local_system() {
    local output_prefix="$OUTPUT_DIR/local_monitor_$TIMESTAMP"

    log "Monitoring local system resources..."

    # CPU usage
    {
        echo "=== CPU Usage Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i++)); do
            echo "$(date '+%H:%M:%S'): $(top -l 1 -n 0 | grep 'CPU usage' || echo 'CPU info not available')"
            sleep 1
        done
    } > "${output_prefix}_cpu.log" &

    # Memory usage
    {
        echo "=== Memory Usage Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i++)); do
            echo "$(date '+%H:%M:%S'): $(vm_stat | grep -E '(Pages free|Pages active|Pages inactive|Pages wired)' | tr '\n' ' ')"
            echo ""
            sleep 1
        done
    } > "${output_prefix}_memory.log" &

    # Network interface statistics (macOS)
    {
        echo "=== Network Interface Statistics ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i++)); do
            echo "$(date '+%H:%M:%S'):"
            netstat -i | grep -E '(en0|en1|lo0)' || echo "Network stats not available"
            echo ""
            sleep 5  # Less frequent for network stats
        done
    } > "${output_prefix}_network.log" &

    # Disk I/O (macOS)
    {
        echo "=== Disk I/O Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i+=5)); do
            echo "$(date '+%H:%M:%S'):"
            iostat -d 1 1 2>/dev/null || echo "iostat not available"
            echo ""
            sleep 5
        done
    } > "${output_prefix}_disk.log" &

    # System load
    {
        echo "=== System Load Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i++)); do
            echo "$(date '+%H:%M:%S'): $(uptime)"
            sleep 1
        done
    } > "${output_prefix}_load.log" &
}

# Function to monitor remote system via Ansible
monitor_remote_system() {
    local ansible_target="gym-server"
    local output_prefix="$OUTPUT_DIR/remote_monitor_$TIMESTAMP"

    log "Monitoring remote system resources via Ansible..."

    # Check if Ansible can connect
    if ! ansible "$ansible_target" -m ping &>/dev/null; then
        warning "Cannot connect to remote system via Ansible"
        return 1
    fi

    # CPU and load monitoring
    {
        echo "=== Remote CPU and Load Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i+=5)); do
            echo "$(date '+%H:%M:%S'):"
            ansible "$ansible_target" -m shell -a "uptime && top -bn1 | head -5" 2>/dev/null || echo "Remote monitoring failed"
            echo ""
            sleep 5
        done
    } > "${output_prefix}_cpu_load.log" &

    # Memory monitoring
    {
        echo "=== Remote Memory Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i+=5)); do
            echo "$(date '+%H:%M:%S'):"
            ansible "$ansible_target" -m shell -a "free -h && df -h /" 2>/dev/null || echo "Remote memory monitoring failed"
            echo ""
            sleep 5
        done
    } > "${output_prefix}_memory_disk.log" &

    # Apache status monitoring
    {
        echo "=== Remote Apache Status Monitor ==="
        echo "Started: $(date)"
        echo ""

        for ((i=1; i<=MONITOR_DURATION; i+=10)); do
            echo "$(date '+%H:%M:%S'):"
            ansible "$ansible_target" -m shell -a "systemctl status httpd --no-pager -l" 2>/dev/null || echo "Apache status check failed"
            echo ""
            sleep 10
        done
    } > "${output_prefix}_apache.log" &
}

# Function to generate monitoring report
generate_monitoring_report() {
    local report_file="$OUTPUT_DIR/monitoring_report_$TIMESTAMP.md"

    log "Generating monitoring report..."

    {
        echo "# System Resource Monitoring Report"
        echo ""
        echo "**Generated:** $(date)"
        echo "**Duration:** $MONITOR_DURATION seconds"
        echo "**Target:** gym-server (192.168.1.11)"
        echo ""

        echo "## Monitoring Summary"
        echo ""

        # Local system summary
        echo "### Local System (Test Client)"
        if [ -f "$OUTPUT_DIR/local_monitor_${TIMESTAMP}_load.log" ]; then
            echo "- **Load average:** $(tail -1 "$OUTPUT_DIR/local_monitor_${TIMESTAMP}_load.log" | grep -o 'load average.*' || echo 'N/A')"
        fi

        if [ -f "$OUTPUT_DIR/local_monitor_${TIMESTAMP}_cpu.log" ]; then
            echo "- **CPU usage:** Last recorded CPU stats available in log"
        fi

        echo ""

        # Remote system summary
        echo "### Remote System (Target Server)"
        if [ -f "$OUTPUT_DIR/remote_monitor_${TIMESTAMP}_cpu_load.log" ]; then
            echo "- **Remote load:** $(grep 'load average' "$OUTPUT_DIR/remote_monitor_${TIMESTAMP}_cpu_load.log" | tail -1 | grep -o 'load average.*' || echo 'N/A')"
        fi

        if [ -f "$OUTPUT_DIR/remote_monitor_${TIMESTAMP}_memory_disk.log" ]; then
            echo "- **Memory status:** Available in detailed logs"
        fi

        echo ""

        echo "## Monitoring Files Generated"
        echo ""
        ls -la "$OUTPUT_DIR"/*"$TIMESTAMP"* | awk '{print "- " $9 " (" $5 " bytes)"}' | sed "s|$OUTPUT_DIR/|- |"
        echo ""

        echo "## Analysis Recommendations"
        echo ""
        echo "- Review CPU usage patterns during load testing"
        echo "- Monitor memory consumption under different loads"
        echo "- Check for any Apache service issues"
        echo "- Analyze network performance correlations"
        echo ""

        echo "## Next Steps"
        echo "1. Correlate monitoring data with performance test results"
        echo "2. Identify resource bottlenecks"
        echo "3. Set up automated monitoring alerts"
        echo "4. Establish baseline resource usage patterns"

    } > "$report_file"

    success "Monitoring report generated: $report_file"
}

# Main execution
main() {
    log "=== SYSTEM RESOURCE MONITORING ==="

    # Start local monitoring
    monitor_local_system

    # Start remote monitoring if available
    monitor_remote_system

    log "Monitoring started. Collecting data for $MONITOR_DURATION seconds..."

    # Wait for monitoring to complete
    sleep "$MONITOR_DURATION"

    log "Monitoring completed. Processing results..."

    # Wait a bit more for background processes to finish
    sleep 5

    # Kill any remaining background processes
    jobs -p | xargs -r kill 2>/dev/null || true

    # Generate report
    generate_monitoring_report

    success "Resource monitoring completed!"
    log "Results available in: $OUTPUT_DIR"
}

# Handle script arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [duration] [output_dir]"
        echo ""
        echo "Arguments:"
        echo "  duration     Monitoring duration in seconds (default: 300)"
        echo "  output_dir   Output directory (default: ./monitoring_output)"
        echo ""
        echo "Examples:"
        echo "  $0                    # Monitor for 5 minutes"
        echo "  $0 60                 # Monitor for 1 minute"
        echo "  $0 180 ./results      # Monitor for 3 minutes, save to ./results"
        exit 0
        ;;
    *)
        main
        ;;
esac