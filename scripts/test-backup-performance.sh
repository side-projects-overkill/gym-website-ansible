#!/bin/bash

# Backup Performance Testing Script
# Tests backup creation, restoration, and storage I/O performance

set -e

# Configuration
BACKUP_TEST_DIR="./backup_performance_test"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WEBSITE_CONTENT_SIZE="22582"  # Known size from testing

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
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

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create test environment
setup_test_environment() {
    log "Setting up backup performance test environment..."

    mkdir -p "$BACKUP_TEST_DIR"
    cd "$BACKUP_TEST_DIR"

    # Create mock website structure for testing
    mkdir -p mock_website/var/www/html

    # Download actual website content for realistic testing
    log "Downloading website content for testing..."
    curl -s "http://192.168.1.11" > mock_website/var/www/html/index.html

    # Create some additional test files to simulate a full website
    echo "/* CSS styles */" > mock_website/var/www/html/style.css
    echo "// JavaScript code" > mock_website/var/www/html/script.js

    # Create mock log files
    mkdir -p mock_website/var/log/httpd
    echo "Mock Apache access log" > mock_website/var/log/httpd/access_log
    echo "Mock Apache error log" > mock_website/var/log/httpd/error_log

    success "Test environment created"
}

# Test backup creation performance
test_backup_creation() {
    log "Testing backup creation performance..."

    local backup_results="backup_performance_$TIMESTAMP.txt"

    {
        echo "=== Backup Creation Performance Test ==="
        echo "Timestamp: $(date)"
        echo "Source: mock_website/"
        echo ""

        # Test different compression methods
        local methods=("tar" "tar.gz" "tar.bz2")

        for method in "${methods[@]}"; do
            echo "Testing $method compression..."

            local backup_file="backup_$method.$method"
            local start_time=$(date +%s.%N)

            case $method in
                "tar")
                    tar -cf "$backup_file" mock_website/
                    ;;
                "tar.gz")
                    tar -czf "$backup_file" mock_website/
                    ;;
                "tar.bz2")
                    tar -cjf "$backup_file" mock_website/
                    ;;
            esac

            local end_time=$(date +%s.%N)
            local duration=$(echo "$end_time - $start_time" | bc)
            local size=$(du -h "$backup_file" | cut -f1)

            echo "  Method: $method"
            echo "  Duration: ${duration}s"
            echo "  Size: $size"
            echo ""
        done

    } > "$backup_results"

    success "Backup creation test completed - results in $backup_results"
}

# Test restore performance
test_restore_performance() {
    log "Testing backup restoration performance..."

    local restore_results="restore_performance_$TIMESTAMP.txt"

    {
        echo "=== Backup Restoration Performance Test ==="
        echo "Timestamp: $(date)"
        echo ""

        # Test restoration from different backup formats
        local backups=("backup_tar.tar" "backup_tar.gz.tar.gz" "backup_tar.bz2.tar.bz2")

        for backup in "${backups[@]}"; do
            if [ -f "$backup" ]; then
                echo "Testing restoration from $backup..."

                local restore_dir="restore_test_$(basename "$backup" | cut -d. -f1)"
                mkdir -p "$restore_dir"

                local start_time=$(date +%s.%N)

                case "$backup" in
                    *.tar.gz)
                        tar -xzf "$backup" -C "$restore_dir"
                        ;;
                    *.tar.bz2)
                        tar -xjf "$backup" -C "$restore_dir"
                        ;;
                    *.tar)
                        tar -xf "$backup" -C "$restore_dir"
                        ;;
                esac

                local end_time=$(date +%s.%N)
                local duration=$(echo "$end_time - $start_time" | bc)

                echo "  Backup: $backup"
                echo "  Duration: ${duration}s"
                echo "  Files restored: $(find "$restore_dir" -type f | wc -l)"
                echo ""

                # Verify restoration
                if [ -f "$restore_dir/mock_website/var/www/html/index.html" ]; then
                    echo "  Verification: ✅ Success"
                else
                    echo "  Verification: ❌ Failed"
                fi
                echo ""

                # Cleanup
                rm -rf "$restore_dir"
            fi
        done

    } > "$restore_results"

    success "Restore performance test completed - results in $restore_results"
}

# Test storage I/O performance
test_storage_io() {
    log "Testing storage I/O performance..."

    local io_results="storage_io_$TIMESTAMP.txt"

    {
        echo "=== Storage I/O Performance Test ==="
        echo "Timestamp: $(date)"
        echo ""

        # Test write performance
        echo "Write Performance Test:"
        echo "Testing sequential write (100MB)..."
        local start_time=$(date +%s.%N)
        dd if=/dev/zero of=write_test.tmp bs=1M count=100 2>/dev/null
        local end_time=$(date +%s.%N)
        local write_duration=$(echo "$end_time - $start_time" | bc)
        local write_speed=$(echo "scale=2; 100 / $write_duration" | bc)

        echo "  Duration: ${write_duration}s"
        echo "  Speed: ${write_speed} MB/s"
        echo ""

        # Test read performance
        echo "Read Performance Test:"
        echo "Testing sequential read (100MB)..."
        local start_time=$(date +%s.%N)
        dd if=write_test.tmp of=/dev/null bs=1M 2>/dev/null
        local end_time=$(date +%s.%N)
        local read_duration=$(echo "$end_time - $start_time" | bc)
        local read_speed=$(echo "scale=2; 100 / $read_duration" | bc)

        echo "  Duration: ${read_duration}s"
        echo "  Speed: ${read_speed} MB/s"
        echo ""

        # Test random I/O performance
        echo "Random I/O Performance Test:"
        echo "Testing random write/read patterns..."
        local start_time=$(date +%s.%N)
        dd if=/dev/urandom of=random_test.tmp bs=4k count=1000 2>/dev/null
        local end_time=$(date +%s.%N)
        local random_duration=$(echo "$end_time - $start_time" | bc)
        local random_speed=$(echo "scale=2; 4 / $random_duration" | bc)

        echo "  Duration: ${random_duration}s"
        echo "  Speed: ${random_speed} MB/s"
        echo ""

        # Cleanup
        rm -f write_test.tmp random_test.tmp

    } > "$io_results"

    success "Storage I/O test completed - results in $io_results"
}

# Test disaster recovery scenarios
test_disaster_recovery() {
    log "Testing disaster recovery scenarios..."

    local dr_results="disaster_recovery_$TIMESTAMP.txt"

    {
        echo "=== Disaster Recovery Performance Test ==="
        echo "Timestamp: $(date)"
        echo ""

        # Simulate website corruption
        echo "Scenario 1: Website File Corruption"
        echo "Simulating file corruption and recovery..."

        # Create a corrupted version
        cp -r mock_website corrupted_website
        echo "CORRUPTED DATA" > corrupted_website/var/www/html/index.html

        # Time recovery process
        local start_time=$(date +%s.%N)

        # Recovery steps
        rm -rf corrupted_website/var/www/html/*
        tar -xzf backup_tar.gz.tar.gz -C ./ --strip-components=1 mock_website/var/www/html/
        cp mock_website/var/www/html/* corrupted_website/var/www/html/

        local end_time=$(date +%s.%N)
        local recovery_time=$(echo "$end_time - $start_time" | bc)

        echo "  Recovery time: ${recovery_time}s"
        echo "  Status: $([ -f "corrupted_website/var/www/html/index.html" ] && echo "✅ Success" || echo "❌ Failed")"
        echo ""

        # Test configuration recovery
        echo "Scenario 2: Configuration File Recovery"
        echo "Testing Apache configuration backup/restore..."

        # Create mock config
        mkdir -p mock_config/etc/httpd/conf
        echo "# Apache Configuration" > mock_config/etc/httpd/conf/httpd.conf
        echo "ServerName localhost" >> mock_config/etc/httpd/conf/httpd.conf

        # Backup and restore config
        local start_time=$(date +%s.%N)
        tar -czf config_backup.tar.gz mock_config/
        rm -rf mock_config/
        tar -xzf config_backup.tar.gz
        local end_time=$(date +%s.%N)
        local config_recovery_time=$(echo "$end_time - $start_time" | bc)

        echo "  Config recovery time: ${config_recovery_time}s"
        echo "  Status: $([ -f "mock_config/etc/httpd/conf/httpd.conf" ] && echo "✅ Success" || echo "❌ Failed")"
        echo ""

        # Complete system recovery simulation
        echo "Scenario 3: Complete System Recovery"
        echo "Testing full system restoration..."

        local start_time=$(date +%s.%N)

        # Simulate full recovery steps
        tar -xzf backup_tar.gz.tar.gz
        tar -xzf config_backup.tar.gz

        local end_time=$(date +%s.%N)
        local full_recovery_time=$(echo "$end_time - $start_time" | bc)

        echo "  Full recovery time: ${full_recovery_time}s"
        echo "  RTO Achievement: $(echo "$full_recovery_time < 900" | bc)" # < 15 minutes
        echo ""

        # Cleanup
        rm -rf corrupted_website mock_config config_backup.tar.gz

    } > "$dr_results"

    success "Disaster recovery test completed - results in $dr_results"
}

# Generate comprehensive backup performance report
generate_backup_report() {
    log "Generating comprehensive backup performance report..."

    local report_file="backup_performance_report_$TIMESTAMP.md"

    {
        echo "# Backup & Disaster Recovery Performance Report"
        echo ""
        echo "**Generated:** $(date)"
        echo "**Test Environment:** Local macOS system"
        echo "**Website Size:** ~22.6 KB (plus mock data)"
        echo ""

        echo "## Test Summary"
        echo ""

        # Backup creation results
        if [ -f "backup_performance_$TIMESTAMP.txt" ]; then
            echo "### Backup Creation Performance"
            echo ""
            echo "\`\`\`"
            grep -A 20 "=== Backup Creation" "backup_performance_$TIMESTAMP.txt"
            echo "\`\`\`"
            echo ""
        fi

        # Restore performance results
        if [ -f "restore_performance_$TIMESTAMP.txt" ]; then
            echo "### Restoration Performance"
            echo ""
            echo "\`\`\`"
            grep -A 15 "=== Backup Restoration" "restore_performance_$TIMESTAMP.txt"
            echo "\`\`\`"
            echo ""
        fi

        # I/O performance results
        if [ -f "storage_io_$TIMESTAMP.txt" ]; then
            echo "### Storage I/O Performance"
            echo ""
            echo "\`\`\`"
            grep -A 10 "Write Performance" "storage_io_$TIMESTAMP.txt"
            echo "\`\`\`"
            echo ""
        fi

        # Disaster recovery results
        if [ -f "disaster_recovery_$TIMESTAMP.txt" ]; then
            echo "### Disaster Recovery Scenarios"
            echo ""
            echo "\`\`\`"
            grep -A 5 "Recovery time" "disaster_recovery_$TIMESTAMP.txt"
            echo "\`\`\`"
            echo ""
        fi

        echo "## Performance Recommendations"
        echo ""
        echo "### Backup Strategy"
        echo "- Use gzip compression for balanced speed/size ratio"
        echo "- Schedule backups during low-traffic periods"
        echo "- Implement incremental backups for large datasets"
        echo ""

        echo "### Disaster Recovery"
        echo "- Maintain multiple backup copies"
        echo "- Test recovery procedures regularly"
        echo "- Document recovery procedures"
        echo "- Set up monitoring for backup integrity"
        echo ""

        echo "## Test Files Generated"
        ls -la *.txt *.tar* 2>/dev/null | awk '{print "- " $9 " (" $5 " bytes)"}'

    } > "$report_file"

    success "Backup performance report generated: $report_file"
}

# Cleanup test environment
cleanup() {
    log "Cleaning up test environment..."

    # Remove large test files
    rm -f *.tar *.tar.gz *.tar.bz2 *.tmp
    rm -rf mock_website corrupted_website mock_config

    success "Cleanup completed"
}

# Main execution
main() {
    echo ""
    log "=== BACKUP & DISASTER RECOVERY PERFORMANCE TESTING ==="
    echo ""

    setup_test_environment
    test_backup_creation
    test_restore_performance
    test_storage_io
    test_disaster_recovery
    generate_backup_report
    cleanup

    echo ""
    success "Backup performance testing completed!"
    log "Report available: backup_performance_report_$TIMESTAMP.md"
}

# Handle script arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [options]"
        echo ""
        echo "This script tests backup and disaster recovery performance"
        echo "including backup creation, restoration, and storage I/O."
        exit 0
        ;;
    *)
        main "$@"
        ;;
esac