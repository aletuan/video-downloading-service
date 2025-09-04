#!/bin/bash
# 
# Test runner convenience script for YouTube Download Service
#
# This script provides simple commands for running tests with coverage reporting.
# It's a wrapper around the more comprehensive test_runner.py script.
#

set -e  # Exit on error

# Get the project root directory (parent of scripts directory)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Show usage information
show_help() {
    echo "YouTube Download Service Test Runner"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  unit           Run unit tests only"
    echo "  integration    Run integration tests only"
    echo "  fast           Run fast tests only (exclude slow/external)"
    echo "  all            Run all tests (default)"
    echo "  coverage       Generate coverage report from existing data"
    echo "  clean          Clean coverage data and reports"
    echo "  watch          Watch for changes and re-run tests"
    echo "  help           Show this help message"
    echo ""
    echo "Options:"
    echo "  --html         Generate HTML coverage report"
    echo "  --xml          Generate XML coverage report"
    echo "  --no-coverage  Disable coverage reporting"
    echo "  --verbose      Enable verbose output"
    echo "  --parallel     Run tests in parallel"
    echo "  --docker       Force Docker execution"
    echo "  --setup        Setup Docker environment before running"
    echo ""
    echo "Docker Integration:"
    echo "  The script automatically detects the best execution environment:"
    echo "  - Uses Docker if available and no local pytest found"
    echo "  - Prefers Docker for consistency in development"
    echo "  - Falls back to local execution if Docker unavailable"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run all tests (auto-detect environment)"
    echo "  $0 unit --html        # Run unit tests with HTML coverage report"
    echo "  $0 fast --parallel    # Run fast tests in parallel"
    echo "  $0 --docker --setup   # Force Docker with environment setup"
    echo "  $0 coverage           # Generate coverage report only"
    echo "  $0 clean              # Clean coverage data"
    echo ""
}

# Check if Python test runner exists
check_test_runner() {
    if [[ ! -f "scripts/test_runner.py" ]]; then
        print_error "Test runner script not found: scripts/test_runner.py"
        exit 1
    fi
}

# Check if Docker is available
check_docker() {
    if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check if we're running inside Docker
is_in_docker() {
    if [[ -f /.dockerenv ]] || [[ "${DOCKER_ENV}" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

# Check if local pytest is available
check_local_pytest() {
    if command -v pytest >/dev/null 2>&1 || python -c "import pytest" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Auto-detect best execution environment
auto_detect_environment() {
    if is_in_docker; then
        echo "local"  # Already in Docker, use local execution
        return
    fi
    
    if check_docker; then
        if ! check_local_pytest; then
            echo "docker"  # No local pytest, use Docker
            return
        fi
        
        # Both available, prefer Docker for consistency
        echo "docker"
    else
        if check_local_pytest; then
            echo "local"  # No Docker, use local if available
        else
            echo "none"   # Neither available
        fi
    fi
}

# Run the Python test runner with arguments
run_test_command() {
    local environment=""
    local force_docker=false
    local setup_docker=false
    
    # Parse Docker-related options
    local args=()
    while [[ $# -gt 0 ]]; do
        case $1 in
            --docker)
                force_docker=true
                args+=("$1")
                shift
                ;;
            --setup)
                setup_docker=true
                args+=("$1")
                shift
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    
    # Determine execution environment
    if [[ "$force_docker" == true ]]; then
        environment="docker"
    else
        environment=$(auto_detect_environment)
    fi
    
    print_status "Detected environment: $environment"
    
    case $environment in
        "docker")
            # Add Docker flags if not already present
            if [[ "$force_docker" != true ]]; then
                args=("--docker" "${args[@]}")
            fi
            if [[ "$setup_docker" == true ]]; then
                args=("--setup" "${args[@]}")
            fi
            
            local cmd="python scripts/test_runner.py ${args[*]}"
            print_status "Running with Docker: $cmd"
            eval $cmd
            ;;
        "local")
            local cmd="python scripts/test_runner.py ${args[*]}"
            print_status "Running locally: $cmd"
            eval $cmd
            ;;
        "none")
            print_error "Neither Docker nor local pytest environment is available!"
            print_warning "Please install Docker or pip install -r requirements-dev.txt"
            return 1
            ;;
        *)
            print_error "Unknown environment: $environment"
            return 1
            ;;
    esac
    
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        print_success "Tests completed successfully"
    else
        print_error "Tests failed with exit code $exit_code"
    fi
    
    return $exit_code
}

# Main script logic
main() {
    # Check dependencies
    check_test_runner
    
    # Handle no arguments (default to all tests)
    if [[ $# -eq 0 ]]; then
        print_status "Running all tests with coverage..."
        run_test_command --all --html
        return $?
    fi
    
    # Parse command
    case "$1" in
        "unit")
            shift
            run_test_command --unit "$@"
            ;;
        "integration") 
            shift
            run_test_command --integration "$@"
            ;;
        "fast")
            shift
            run_test_command --fast "$@"
            ;;
        "all")
            shift
            run_test_command --all "$@"
            ;;
        "coverage")
            shift
            run_test_command --coverage-only "$@"
            ;;
        "clean")
            shift
            run_test_command --clean "$@"
            ;;
        "watch")
            shift
            run_test_command --watch "$@"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            # Check if it's an option (starts with --)
            if [[ "$1" == --* ]]; then
                # Treat as options for all tests
                run_test_command --all "$@"
            else
                print_error "Unknown command: $1"
                echo ""
                show_help
                exit 1
            fi
            ;;
    esac
}

# Run main function with all arguments
main "$@"